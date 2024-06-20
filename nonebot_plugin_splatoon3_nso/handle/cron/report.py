import asyncio
import datetime
import time

from .utils import cron_logger, user_remove_duplicates
from datetime import datetime as dt, timedelta

from ..report import get_report
from ..send_msg import notify_to_private, cron_notify_to_channel
from ...data.db_sqlite import Report
from ...handle.utils import get_battle_time_or_coop_time, get_game_sp_id
from ...data.data_source import model_add_report, model_get_all_user, dict_get_or_set_user_info, model_get_or_set_user, \
    model_get_today_report, dict_clear_user_info_dict, model_get_temp_image_path, global_user_info_dict
from ...s3s.splatoon import Splatoon
from ...utils import get_msg_id, convert_td
from ...utils.bot import *


async def create_set_report_tasks():
    """8点时请求并提前写好日报数据"""
    cron_msg = f'create_set_report_tasks start'
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("set_report", "start")

    t = dt.utcnow()
    users = model_get_all_user()
    # 去重
    users = user_remove_duplicates(users)

    list_user: list[tuple] = []  # 简要记录平台和user_id信息，等到具体任务内再获取user数据
    for user in users:
        list_user.append((user.platform, user.user_id))

    _pool = 10
    set_report_count = 0
    for i in range(0, len(list_user), _pool):
        p_and_id_list = list_user[i:i + _pool]
        tasks = [set_user_report_task(p_and_id) for p_and_id in p_and_id_list]
        res = await asyncio.gather(*tasks)
        # 统计有多少人更新了日报
        for r in res:
            if r:
                set_report_count += 1

    # 清理任务字典
    cron_logger.info(f'clear cron user_info_dict...')
    clear_count = await dict_clear_user_info_dict(_type="cron")

    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = f"create_set_report_tasks end: {str_time}\n" \
               f"set_report_count: {set_report_count}\n" \
               f"clear_count: {clear_count}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("set_report", "end", f"耗时:{str_time}\n写日报: {set_report_count}\n清理对象: {clear_count}")


async def set_user_report_task(p_and_id):
    """任务:写用户最后游玩数据以及日报数据"""
    platform, user_id = p_and_id
    msg_id = get_msg_id(platform, user_id)
    # token复用，如果在公共缓存存在该用户，直接使用该缓存对象而不是创建新对象
    global_user_info = global_user_info_dict.get(msg_id)
    if global_user_info:
        u = global_user_info
        if not u or not u.session_token:
            return
        splatoon = Splatoon(None, None, u)
    else:
        # 新建cron任务对象
        u = dict_get_or_set_user_info(platform, user_id, _type="cron")
        if not u or not u.session_token:
            return
        splatoon = Splatoon(None, None, u, _type="cron")
        try:
            # 刷新token
            await splatoon.refresh_gtoken_and_bullettoken()
        except ValueError as e:
            if 'invalid_grant' in str(e) or 'Membership required' in str(e) or "has be banned" in str(e):
                # 无效登录或会员过期 或被封禁
                # 关闭连接池
                await splatoon.req_client.close()
                return False
        except Exception as e:
            # 这里刷新token失败没太大影响，后续在请求时仍会刷新token
            cron_logger.warning(f'set_user_report_task error: {msg_id},refresh_gtoken_and_bullettoken error:{e}')
    try:
        cron_logger.debug(f'set_user_report: {msg_id}, {u.user_name}')
        # 个人摘要数据
        res_summary = await splatoon.get_history_summary()
        if not res_summary:
            res_summary = await splatoon.get_history_summary(multiple=True)
        history = res_summary['data']['playHistory']
        player = res_summary['data']['currentPlayer']
        first_play_time = history['gameStartTime']
        first_play_time = dt.strptime(first_play_time, '%Y-%m-%dT%H:%M:%SZ')
        game_name = player['name']
        # 从个人数据缓存头像
        # 我的头像，使用sp_id进行储存
        icon_img = await model_get_temp_image_path('my_icon', u.game_sp_id, player['userIcon']['url'])

        # 最近对战数据
        res_battle = await splatoon.get_recent_battles(multiple=True)
        if not res_battle:
            res_battle = await splatoon.get_recent_battles(multiple=True)
        b_info = res_battle['data']['latestBattleHistories']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]
        battle_t = get_battle_time_or_coop_time(b_info['id'])
        game_sp_id = get_game_sp_id(b_info['player']['id'])

        # 最近打工数据
        res_coop = await splatoon.get_coops(multiple=True)
        if not res_coop:
            res_coop = await splatoon.get_coops(multiple=True)
        coop_id = res_coop['data']['coopResult']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]['id']
        coop_t = get_battle_time_or_coop_time(coop_id)

        last_play_time = max(dt.strptime(battle_t, '%Y%m%dT%H%M%S'), dt.strptime(coop_t, '%Y%m%dT%H%M%S'))

        # 更新用户游玩记录
        model_get_or_set_user(platform, user_id, game_name=game_name, game_sp_id=game_sp_id,
                              first_play_time=first_play_time, last_play_time=last_play_time)

        # 上次游玩时间位于一天内
        if last_play_time.date() >= (dt.utcnow() - timedelta(days=1)).date():
            # 写新的日报
            await set_user_report(u, res_summary, res_coop, last_play_time, splatoon, game_sp_id)
            cron_logger.info(f'set_user_report_task success: {msg_id}')
            return True

    except Exception as ex:
        cron_logger.warning(f'set_user_report_task error: {msg_id}, error:{ex}')
    finally:
        # 关闭连接池
        await splatoon.req_client.close()


async def set_user_report(u, res_summary, res_coop, last_play_time, splatoon, player_code):
    """写用户日报数据"""
    # 总对战数目
    all_data = await splatoon.get_total_query(multiple=True)
    if not all_data:
        all_data = await splatoon.get_total_query(multiple=True)

    history = res_summary['data']['playHistory']
    player = res_summary['data']['currentPlayer']
    nickname = player['name']

    total_cnt = all_data['data']['playHistory']['battleNumTotal']
    win_cnt = history['winCountTotal']
    lose_cnt = total_cnt - win_cnt
    win_rate = round(win_cnt / total_cnt * 100, 2)

    _l = history['leagueMatchPlayHistory']
    _ln = _l['attend'] - _l['gold'] - _l['silver'] - _l['bronze']
    _o = history['bankaraMatchOpenPlayHistory']
    _on = _o['attend'] - _o['gold'] - _o['silver'] - _o['bronze']

    ar = round((history.get('xMatchMaxAr') or {}).get('power') or 0, 2) or None
    lf = round((history.get('xMatchMaxLf') or {}).get('power') or 0, 2) or None
    gl = round((history.get('xMatchMaxGl') or {}).get('power') or 0, 2) or None
    cl = round((history.get('xMatchMaxCl') or {}).get('power') or 0, 2) or None
    max_power = max(ar or 0, lf or 0, gl or 0, cl or 0) or None

    coop = res_coop['data']['coopResult']
    card = coop['pointCard']
    p = coop['scale']

    _report = {
        'user_id': u.db_id,
        'user_id_sp': player_code,
        'nickname': nickname,
        'name_id': player['nameId'],
        'byname': player['byname'],
        'rank': history['rank'],
        'udemae': history['udemae'],
        'udemae_max': history['udemaeMax'],
        'total_cnt': total_cnt,
        'win_cnt': win_cnt,
        'lose_cnt': lose_cnt,
        'win_rate': win_rate,
        'paint': history['paintPointTotal'],
        'badges': len(history['badges']),
        'event_gold': _l['gold'],
        'event_silver': _l['silver'],
        'event_bronze': _l['bronze'],
        'event_none': _ln,
        'open_gold': _o['gold'],
        'open_silver': _o['silver'],
        'open_bronze': _o['bronze'],
        'open_none': _on,
        'max_power': max_power,
        'x_ar': ar,
        'x_lf': lf,
        'x_gl': gl,
        'x_cl': cl,
        'coop_cnt': card['playCount'],
        'coop_gold_egg': card['goldenDeliverCount'],
        'coop_egg': card['deliverCount'],
        'coop_boss_cnt': card['defeatBossCount'],
        'coop_rescue': card['rescueCount'],
        'coop_point': card['totalPoint'],
        'coop_gold': p['bronze'],
        'coop_silver': p['silver'],
        'coop_bronze': p['gold'],
        'last_play_time': last_play_time,
    }
    if player_code:
        new_report = Report(**_report)
        model_add_report(new_report)


async def send_report_task():
    """9点时进行发信"""
    report_logger = logger.bind(report=True)
    cron_msg = f'create_send_report_tasks start'
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("send_report", "start")
    t = dt.utcnow()

    users = model_get_all_user()
    for user in users:
        # 排除qq平台发信 和 日报通知未打开的用户
        if user.platform == "QQ" or not user.report_notify:
            continue
        msg_id = get_msg_id(user.platform, user.user_id)
        # 根据sp_id查询今天是否生成新日报
        have_report = model_get_today_report(user.game_sp_id)
        if not have_report:
            continue
        # 每次循环强制睡眠1s，使一分钟内不超过120次发信阈值
        time.sleep(1)
        try:
            msg = get_report(user.platform, user.user_id, _type="cron")
            if msg:
                # 写日志
                log_msg = msg.replace('\n', '')
                report_logger.info(f"get {msg_id} report：{log_msg}")
                # # 通知到频道
                # await report_notify_to_channel(user.platform, user.user_id, msg, _type='job')
                # 通知到私信
                msg += "\n/report_notify close 关闭每日日报推送"
                await notify_to_private(user.platform, user.user_id, msg)
        except Kook_ActionFailed as e:
            if e.status_code == 40000:
                if e.message.startswith("无法发起私信"):
                    time.sleep(10)
                elif e.message.startswith("你已被对方屏蔽"):
                    model_get_or_set_user(user.platform, user.user_id, stat_notify=0, report_notify=0)
                    cron_logger.warning(
                        f'create_send_report_tasks error:{msg_id},error:用户已屏蔽发信bot，已关闭其通知权限')
            continue
        except Exception as e:
            cron_logger.warning(f'create_send_report_tasks error:{msg_id},error:{e}')
            continue

    # 清理任务字典
    cron_logger.info(f'clear cron user_info_dict...')
    clear_count = await dict_clear_user_info_dict(_type="cron")
    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = f"create_send_report_tasks end: {str_time}\nclear_count: {clear_count}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("send_report", "end", f"耗时:{str_time}\n清理对象: {clear_count}")
