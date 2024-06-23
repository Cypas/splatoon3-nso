import copy
import datetime
from typing import Type

from nonebot import logger
from sqlalchemy import and_, text

from .db_sqlite import *
from .utils import model_get_or_set_temp_image, get_insert_or_update_obj, GlobalUserInfo
from ..utils import get_or_init_client, get_msg_id, ReqClient

global_user_info_dict: dict[str:GlobalUserInfo] = {}  # 用于缓存今日已使用过指令的用户，并为这些活跃用户定期更新token

global_cron_user_info_dict: dict[str:GlobalUserInfo] = {}  # 定时任务专用的字典，用完即销毁


def dict_get_or_set_user_info(platform, user_id, _type="normal", **kwargs):
    """获取 或 更新 用户信息
    优先读取字典内信息，没有则查询数据库
    """
    global global_user_info_dict
    global global_cron_user_info_dict
    key = get_msg_id(platform, user_id)

    # 选择不同的字典
    user_dict = {}
    if _type == "normal":
        user_dict = global_user_info_dict
    elif _type == "cron":
        # 定时任务
        user_dict = global_cron_user_info_dict

    user_info = user_dict.get(key)
    if not user_info:
        # 不存在，从数据库获取信息再写入字典
        user = model_get_or_set_user(platform, user_id)
        if user:
            user_info = GlobalUserInfo(
                db_id=user.id,
                platform=user.platform,
                user_id=user.user_id,
                user_name=user.user_name,
                session_token=user.session_token,
                g_token=user.g_token,
                bullet_token=user.bullet_token,
                access_token=user.access_token,
                game_name=user.game_name or "",
                game_sp_id=user.game_sp_id,
                push=0,
                push_cnt=user.push_cnt or 0,
                cmd_cnt=user.cmd_cnt or 0,
                user_agreement=user.user_agreement or 0,
                stat_key=user.stat_key,
                ns_name=user.ns_name,
                ns_friend_code=user.ns_friend_code,
                req_client=get_or_init_client(platform, user_id, _type)
            )
            user_dict.update({key: user_info})
        else:
            # 该用户未登录
            user_info = GlobalUserInfo(
                platform=platform,
                user_id=user_id)

    if len(kwargs) != 0:
        # 更新字典
        if not user_info:
            user_info = GlobalUserInfo(platform=platform, user_id=user_id)
        for k, v in kwargs.items():
            if hasattr(user_info, k):
                setattr(user_info, k, v)

        user_dict.update({key: user_info})

        # 更新数据库
        user = model_get_or_set_user(platform, user_id, **kwargs)
        if not user:
            logger.debug(f"user info update error; {kwargs}")
    return user_info


def dict_get_all_global_users(remove_duplicates=True) -> list[GlobalUserInfo]:
    """获取全部公共缓存用户"""

    def user_remove_duplicates(lst: list[GlobalUserInfo]):
        # 根据game_sp_id去重全部users
        result = []
        for u in lst:
            if u.user_agreement == 1:
                if u.game_sp_id and u.game_sp_id not in [r.game_sp_id for r in result]:
                    result.append(u)
        return result

    users: list[GlobalUserInfo] = list(global_user_info_dict.values())
    # 去重
    if remove_duplicates:
        users = user_remove_duplicates(users)
    return users


async def dict_clear_user_info_dict(_type: str) -> int:
    """关闭client对象，然后清空该类型用户字典"""
    # 选择不同的字典
    user_dict = {}
    if _type == "normal":
        user_dict = global_user_info_dict
    elif _type == "cron":
        # 定时任务
        user_dict = global_cron_user_info_dict
    count = len(user_dict)
    # 关闭全部client
    await ReqClient.close_all(_type)
    # 清空字典
    user_dict.clear()
    return count


async def dict_clear_one_user_info_dict(platform, user_id):
    """清空某一用户的字典和client对象"""
    global global_user_info_dict
    key = get_msg_id(platform, user_id)
    # 删除缓存
    if key in global_user_info_dict:
        global_user_info_dict.pop(key)
        # 关闭client
        client = get_or_init_client(platform, user_id)
        await client.close()


async def model_get_temp_image_path(_type, name, link=None) -> str:
    """获取缓存文件路径"""
    row = await model_get_or_set_temp_image(_type, name, link=link)
    # logger.info(f"row为{row.__dict__}")

    if row and row.file_name:
        # 存在有效本地缓存
        path = f"{DIR_TEMP_IMAGE}/{_type}/{row.file_name}"
    else:
        # 没有缓存数据或无效缓存 默认返回空，不渲染图片
        path = ""

    return path


def model_clean_db_cache():
    """整理数据库内存碎片"""
    session = DBSession()
    session.execute(text("VACUUM"))
    session.commit()
    session.close()

    session2 = DBSession_Friends()
    session2.execute(text("VACUUM"))
    session2.commit()
    session2.close()


def model_get_or_set_user(platform, user_id, **kwargs) -> UserTable:
    """获取或插入或更新user信息"""
    logger.debug(f"get_or_set_user: {kwargs}")
    try:
        session = DBSession()
        filter_dict = {"platform": platform, "user_id": user_id}
        if len(kwargs) != 0:
            user = get_insert_or_update_obj(UserTable, filter_dict, platform=platform, user_id=user_id, **kwargs)
        else:
            user = get_insert_or_update_obj(UserTable, filter_dict)
        if user:
            # 这里的session.add本质上执行了create或update的操作，现有user对象所绑定的session已经close，直接用user去commit会报错
            session.add(copy.deepcopy(user))
        session.commit()
        session.close()
        return user

    except Exception as e:
        logger.error(f"model_get_or_set_user error: {e}")
        return None


def model_delete_user(platform, user_id):
    """删除用户"""
    session = DBSession()
    session.query(UserTable).filter(UserTable.platform == platform, UserTable.user_id == user_id).delete()
    session.commit()
    session.close()


def model_get_all_user() -> list[UserTable]:
    """获取全部session_token不为空用户"""
    session = DBSession()
    users = session.query(UserTable).filter(UserTable.session_token.isnot(None), UserTable.user_agreement == 1).all()
    session.close()
    return users


def model_get_all_stat_user() -> list[UserTable]:
    """获取全部session_token不为空,且stat key不为空用户"""
    session = DBSession()
    users = session.query(UserTable).filter(
        and_(UserTable.session_token.isnot(None), UserTable.stat_key.isnot(None), UserTable.user_agreement == 1)).all()
    session.close()
    return users


def model_get_another_account_user(platform, user_id) -> list[Type[UserTable]]:
    """查找同game_sp_id的其他账号"""
    session = DBSession()
    # 查找账号id
    subq = session.query(UserTable.id.label("sub_id"), UserTable.game_sp_id.label("sub_game_sp_id")).filter(
        and_(UserTable.platform == platform, UserTable.user_id == user_id)).subquery()
    # 查找sp_id但非本账号id
    users = session.query(UserTable).filter(
        and_(UserTable.game_sp_id.isnot(None), UserTable.game_sp_id == subq.c.sub_game_sp_id,
             UserTable.id != subq.c.sub_id)).all()
    session.close()
    return users


def model_get_newest_user() -> UserTable:
    """获取最新登录的一个用户，没那么容易出问题"""
    session = DBSession()
    user = session.query(UserTable).order_by(UserTable.create_time.desc()).first()
    session.close()
    return user


def model_get_login_user_by_sp_code(player_code):
    """获取登录用户信息"""
    session = DBSession()
    user = session.query(UserTable).filter(
        and_(UserTable.game_sp_id == player_code, UserTable.game_sp_id.isnot(None))).first()
    session.close()
    return user


def model_get_top_player(player_code):
    """获取一名top玩家信息"""
    session = DBSession()
    user = session.query(TopPlayer).filter(
        TopPlayer.player_code == player_code).order_by(TopPlayer.power.desc()).first()
    session.close()
    return user


def model_get_max_power_top_all(player_code) -> TopAll:
    """获取一条最高分数 top all信息"""
    session = DBSession()
    user = session.query(TopAll).filter(
        TopAll.player_code == player_code).order_by(TopAll.power.desc()).first()
    session.close()
    return user


def model_get_all_top_all(player_code):
    """获取某人全部上榜数据"""
    session = DBSession()
    user = session.query(TopAll).filter(TopAll.player_code == player_code).all()
    session.close()
    return user


# def model_get_all_weapon() -> dict:
#     """获取全部装备数据"""
#     session = DBSession()
#     weapon = session.query(Weapon).all()
#     _dict = dict((str(i.weapon_id), dict(name=i.weapon_name, url=i.image2d_thumb)) for i in weapon)
#     session.commit()
#     session.close()
#     return _dict

# def model_add_report(**kwargs):
#     """添加日报数据"""
#     report_logger = logger.bind(report=True)
#     report_logger.debug(f"model_add_report: {kwargs}")
#     _dict = kwargs
#     user_id_sp = _dict.get("user_id_sp")
#     if not user_id_sp:
#         report_logger.warning(f"no user_id_sp: {_dict}")
#         return
#     session = DBSession()
#     _res = session.query(Report).filter(Report.user_id_sp == user_id_sp).order_by(Report.create_time.desc()).first()
#     if _res and _res.create_time.date() >= datetime.datetime.utcnow().date():
#         report_logger.debug(f'already saved report: {_dict.get("user_id")}, {user_id_sp}, {_dict.get("nickname")}')
#         session.close()
#         return
#
#     new_report = Report(**_dict)
#     session.add(new_report)
#     session.commit()
#     session.close()


def model_add_report(new_report: Report):
    """添加日报数据"""
    report_logger = logger.bind(report=True)
    report_logger.debug(f"model_add_report: {new_report}")
    user_id_sp = new_report.user_id_sp
    if not user_id_sp:
        report_logger.warning(f"no user_id_sp: {new_report}")
        return
    session = DBSession()
    _res = session.query(Report).filter(Report.user_id_sp == user_id_sp).order_by(Report.create_time.desc()).first()
    # 避免一天内多次写入
    if _res and _res.create_time.date() >= datetime.datetime.utcnow().date():
        report_logger.debug(f'already saved report: db_id: {new_report.user_id}, {user_id_sp}, {new_report.nickname}')
        session.close()
        return

    session.add(new_report)
    session.commit()
    session.close()


def model_get_today_report(user_id_sp):
    """获取今日日报数据 用于判断日报是否需要推送"""
    if not user_id_sp:
        return None
    session = DBSession()
    report = session.query(Report).filter(
        and_(Report.user_id_sp == user_id_sp,
             Report.create_time > datetime.datetime.utcnow() - datetime.timedelta(hours=4))).first()
    session.close()
    return report


def model_get_report(user_id_sp, create_time=""):
    """获取日报"""
    if not user_id_sp:
        return None
    session = DBSession()

    #     query = [Report.user_id_sp == user_id_sp]
    #     report = session.query(Report).filter(*query).order_by(Report.create_time.desc()).all()

    if not create_time:
        report = session.query(Report).from_statement(text("""
    SELECT *
    FROM report WHERE (user_id_sp, last_play_time, create_time) IN
    ( SELECT user_id_sp, last_play_time, MAX(create_time)
      FROM report
      GROUP BY user_id_sp, last_play_time)
    and user_id_sp=:user_id_sp
    order by create_time desc
    limit 30""")
                                                      ).params(user_id_sp=user_id_sp).all()
    else:
        report = session.query(Report).from_statement(text("""
        SELECT *
        FROM report WHERE (user_id_sp, last_play_time, create_time) IN
        ( SELECT user_id_sp, last_play_time, MAX(create_time)
          FROM report
          GROUP BY user_id_sp, last_play_time)
        and user_id_sp=:user_id_sp and create_time>=:create_time
        order by create_time desc""")
                                                      ).params(user_id_sp=user_id_sp, create_time=create_time).all()
    session.close()
    return report


def model_get_report_all(user_id_sp):
    """获取全部日报"""
    if not user_id_sp:
        return None
    session = DBSession()
    data = session.execute(text(f"""
SELECT id, DATETIME(last_play_time, '+8 hours') as last_play_time,
total_cnt,
total_cnt - LAG(total_cnt) OVER (ORDER BY last_play_time) AS total_inc_cnt,
win_cnt, win_rate,
round(win_rate - LAG(win_rate) OVER (ORDER BY last_play_time), 2) AS win_rate_change,
coop_cnt,
coop_cnt - LAG(coop_cnt) OVER (ORDER BY last_play_time) AS coop_inc_cnt,
coop_boss_cnt,
coop_boss_cnt - LAG(coop_boss_cnt) OVER (ORDER BY last_play_time) AS coop_boss_change,
rank, udemae
FROM report WHERE (user_id_sp, last_play_time, create_time) IN
( SELECT user_id_sp, last_play_time, MAX(create_time)
  FROM report
  GROUP BY user_id_sp, last_play_time)
and user_id_sp='{user_id_sp}'
order by create_time desc
limit 60
""")).all()

    reports = [row._mapping for row in data]
    session.close()
    return reports


def model_get_user_friend(game_name) -> UserFriendTable:
    """获取好友数据"""
    session = DBSession_Friends()
    user = session.query(UserFriendTable).filter(
        UserFriendTable.game_name == game_name
    ).order_by(UserFriendTable.create_time.desc()).first()
    session.close()
    return user


def model_set_user_friend(data_lst):
    """设置好友数据"""
    report_logger = logger.bind(report=True)
    session = DBSession_Friends()
    for r in data_lst:
        user = session.query(UserFriendTable).filter(UserFriendTable.friend_id == r[1]).first()
        game_name = r[2] or r[3]
        # user = copy.deepcopy(u)
        # session.commit()
        if user:
            is_change = False
            if r[2] and user.game_name != game_name:
                is_change = True
            if is_change is False and user.user_icon != r[4]:
                is_change = True

            if is_change:
                report_logger.debug(f'change {user.id:>5}, {user.player_name}, {user.nickname}, {user.game_name}')
                report_logger.debug(f'cha--> {user.id:>5}, {r[2]}, {r[3]}, {game_name}')
                user.player_name = r[2]
                user.nickname = r[3]
                user.user_icon = r[4]
                user.game_name = game_name
                session.commit()
                report_logger.debug(f'edit user_friend: {user.id:>5}, {r[1]}, {r[2]}, {r[3]}, {game_name}')

        else:
            _dict = {
                'user_id': '',
                'friend_id': r[1],
                'player_name': r[2],
                'nickname': r[3],
                'game_name': game_name,
                'user_icon': r[4],
            }
            new_user = UserFriendTable(**_dict)
            session.add(new_user)
            session.commit()
            report_logger.debug(f'add user_friend: {r[1]}, {r[2]}, {r[3]}, {game_name}')

    session.close()


def model_delete_top_player(top_id):
    """删除指定赛季 top榜单玩家数据"""
    session = DBSession()
    session.query(TopPlayer).filter(TopPlayer.top_id == top_id).delete()
    session.commit()
    session.close()


def model_delete_top_all(top_id):
    """删除指定赛季 top_all榜单玩家数据"""
    session = DBSession()
    session.query(TopAll).filter(TopAll.top_id == top_id).delete()
    session.commit()
    session.close()


def model_add_top_player(row):
    """添加top榜单数据"""
    top_id, _top_type, rank, power, name, name_id, player_code, byname, weapon_id, weapon = row

    session = DBSession()
    _dict = {
        'top_id': top_id,
        'top_type': _top_type,
        'rank': rank,
        'power': power,
        'player_name': name,
        'player_name_id': name_id,
        'player_code': player_code,
        'byname': byname,
        'weapon_id': weapon_id,
        'weapon': weapon,
    }
    new_user = TopPlayer(**_dict)
    session.add(new_user)
    session.commit()
    session.close()


def model_add_top_all(row):
    """添加top_all榜单数据"""
    top_id, _top_type, rank, power, name, name_id, player_code, byname, weapon_id, weapon, play_time = row

    session = DBSession()
    _dict = {
        'top_id': top_id,
        'top_type': _top_type,
        'rank': rank,
        'power': power,
        'player_name': name,
        'player_name_id': name_id,
        'player_code': player_code,
        'byname': byname,
        'weapon_id': weapon_id,
        'weapon': weapon,
        'play_time': play_time
    }
    new_user = TopAll(**_dict)
    session.add(new_user)
    session.commit()
    session.close()


def model_get_top_all_count_by_top_type(top_type):
    """通过top_all类型取得top_all记录的count"""
    session = DBSession()
    top_count = session.query(func.count(TopAll.id)).where(TopAll.top_type.contains(top_type)).scalar()
    session.close()
    return top_count


# def model_get_newest_event_top_all():
#     """获取最新的event比赛排行榜数据"""
#     """
#     SELECT
#         *,
#         top_all.top_type
#     FROM
#         top_all
#     WHERE
#         top_all.top_type LIKE 'LeagueMatchRankingTeam%'
#     GROUP BY
#         top_all.top_type
#     ORDER BY
#         top_all.create_time DESC
#     """
#     session = DBSession()
#     top = session.query(TopAll).where(TopAll.top_type.like("LeagueMatchRankingTeam%")).group_by(TopAll.top_type) \
#         .order_by(TopAll.create_time.desc()).first()
#     session.close()
#     return top


def model_get_power_rank():
    session = DBSession()
    data = session.execute(text(f"""
select user_id_sp, max(max_power) max_power,
       row_number() over (order by max_power desc) rank
from report r
group by user_id_sp
order by max_power desc
""")).all()

    res = [row._mapping for row in data]
    session.close()
    return dict((str(i.user_id_sp), i.rank) for i in res)
