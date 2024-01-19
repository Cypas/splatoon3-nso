from .db_sqlite import *
from .utils import model_get_or_set_temp_image, get_insert_or_update_obj, GlobalUserInfo
from ..utils import get_or_init_client, get_msg_id

global_user_info_dict: dict[str:GlobalUserInfo] = {}  # 用于缓存今日已使用过指令的用户，并为这些活跃用户定期更新token


def dict_get_or_set_user_info(platform, user_id, **kwargs):
    """获取 或 更新 用户信息
    优先读取字典内信息，没有则查询数据库
    """
    global global_user_info_dict
    key = get_msg_id(platform, user_id)
    user_info = global_user_info_dict.get(key)
    if not user_info:
        # 不存在，从数据库获取信息再写入字典
        user = model_get_or_set_user(platform, user_id)
        if user:
            user_info = GlobalUserInfo(
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
                stat_key=user.stat_key,
                req_client=get_or_init_client(platform, user_id)
            )
            global_user_info_dict.update({key: user_info})
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
        global_user_info_dict.update({key: user_info})
        # 更新数据库
        user = model_get_or_set_user(platform, user_id, **kwargs)
        if not user:
            logger.debug(f"user info update error; {kwargs}")
    return user_info


async def model_get_temp_image_path(_type, name, link) -> str:
    """获取缓存文件路径"""
    row = await model_get_or_set_temp_image(_type, name, link)
    # logger.info(f"row为{row.__dict__}")
    file_name = row.file_name
    return f"{DIR_TEMP_IMAGE}/{_type}/{file_name}"


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
    logger.debug(f'get_or_set_user: {kwargs}')
    try:
        session = DBSession()
        filter_dict = {"platform": platform, "user_id": user_id}
        if len(kwargs) != 0:
            user = get_insert_or_update_obj(UserTable, filter_dict, platform=platform, user_id=user_id, **kwargs)
        else:
            user = get_insert_or_update_obj(UserTable, filter_dict)
        if user:
            session.add(copy.deepcopy(user))
        session.commit()
        session.close()
        return user

    except Exception as e:
        logger.error(f'get_or_set_user error: {e}')
        return None


def model_delete_user(platform, user_id):
    """删除用户"""
    session = DBSession()
    session.query(UserTable).filter(UserTable.platform == platform, UserTable.user_id == user_id).delete()
    session.commit()
    session.close()


def model_get_all_user():
    """获取全部用户"""
    session = DBSession()
    users = session.query(UserTable).all()
    new_users = copy.deepcopy(users)
    session.commit()
    session.close()
    return new_users


def model_get_login_user(player_code):
    session = DBSession()
    user = session.query(UserTable).filter(UserTable.game_sp_id == player_code).first()
    new_user = copy.deepcopy(user)
    session.commit()
    session.close()
    return new_user


def model_get_top_player(player_code):
    """获取一名top玩家信息"""
    session = DBSession()
    user = session.query(TopPlayer).filter(
        TopPlayer.player_code == player_code).order_by(TopPlayer.power.desc()).first()
    new_user = copy.deepcopy(user)
    session.commit()
    session.close()
    return new_user


def model_get_top_all(player_code) -> TopAll:
    """获取一条top all信息"""
    session = DBSession()
    user = session.query(TopAll).filter(
        TopAll.player_code == player_code).order_by(TopAll.power.desc()).first()
    new_user = copy.deepcopy(user)
    session.commit()
    session.close()
    return new_user


def model_get_all_weapon() -> dict:
    """获取全部装备数据"""
    session = DBSession()
    weapon = session.query(Weapon).all()
    _dict = dict((str(i.weapon_id), dict(name=i.weapon_name, url=i.image2d_thumb)) for i in weapon)
    session.commit()
    session.close()
    return _dict


def model_get_user_friend(game_name) -> UserFriendTable:
    """获取好友数据"""
    session = DBSession_Friends()
    user = session.query(UserFriendTable).filter(
        UserFriendTable.game_name == game_name
    ).order_by(UserFriendTable.create_time.desc()).first()
    new_user = copy.deepcopy(user)
    session.commit()
    session.close()
    return new_user


def model_set_user_friend(data_lst):
    """设置好友数据"""
    report_logger = logger.bind(report=True)
    session = DBSession_Friends()
    for r in data_lst:
        u = session.query(UserFriendTable).filter(UserFriendTable.friend_id == r[1]).first()
        game_name = r[2] or r[3]
        user = copy.deepcopy(u)
        session.commit()
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
