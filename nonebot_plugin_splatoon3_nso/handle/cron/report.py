import asyncio
import os
import time

from .utils import cron_logger, user_remove_duplicates
from datetime import datetime as dt, timedelta

from ..report import get_report
from ..send_msg import notify_to_private
from ... import DIR_RESOURCE, get_battle_time_or_coop_time, get_game_sp_id
from ...data.data_source import model_add_report, model_get_all_user, dict_get_or_set_user_info, model_get_or_set_user
from ...s3s.splatoon import Splatoon
from ...utils import get_msg_id


async def create_set_report_tasks():
    """7点时请求并提前写好日报数据"""
    cron_logger.info(f'create_set_report_tasks start')
    t = dt.utcnow()
    users = model_get_all_user()
    # 去重
    users = user_remove_duplicates(users)
    # users = sorted(users, key=lambda x: (-(x.report_type or 0), x.id))

    list_user: list[tuple] = []  # 简要记录平台和user_id信息，等到具体任务内再获取user数据
    for user in users:
        list_user.append((user.platform, user.user_id))

    _pool = 50
    for i in range(0, len(list_user), _pool):
        _p_and_id_list = list_user[i:i + _pool]
        tasks = [set_user_report_task(p_and_id) for p_and_id in _p_and_id_list]
        res = await asyncio.gather(*tasks)

    cron_logger.info(f'create_set_report_tasks end: {dt.utcnow() - t}')


async def set_user_report_task(p_and_id):
    """任务:写用户最后游玩数据以及日报数据"""
    platform, user_id = p_and_id
    msg_id = get_msg_id(platform, user_id)
    try:
        u = dict_get_or_set_user_info(platform, user_id)
        if not u or not u.session_token:
            return

        cron_logger.debug(
            f'set_user_info: {msg_id}, {u.user_name}')
        splatoon = Splatoon(None, None, u)

        # 个人摘要数据
        res_summary = await splatoon.get_history_summary()
        history = res_summary['data']['playHistory']
        player = res_summary['data']['currentPlayer']
        first_play_time = history['gameStartTime']
        first_play_time = dt.strptime(first_play_time, '%Y-%m-%dT%H:%M:%SZ')
        game_name = player['name']

        # 最近对战数据
        res_battle = await splatoon.get_recent_battles()
        b_info = res_battle['data']['latestBattleHistories']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]
        battle_t = get_battle_time_or_coop_time(b_info['id'])
        game_sp_id = get_game_sp_id(b_info['player']['id'])

        # 最近打工数据
        res_coop = await splatoon.get_coops()
        coop_id = res_coop['data']['coopResult']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]['id']
        coop_t = get_battle_time_or_coop_time(coop_id)

        last_play_time = max(dt.strptime(battle_t, '%Y%m%dT%H%M%S'), dt.strptime(coop_t, '%Y%m%dT%H%M%S'))

        # 更新用户游玩记录
        model_get_or_set_user(platform, user_id, game_name=game_name, game_sp_id=game_sp_id,
                              first_play_time=first_play_time, last_play_time=last_play_time)

        if last_play_time.date() >= (dt.utcnow() - timedelta(days=1)).date():
            # 写新的日报
            await set_user_report(u, res_summary, res_coop, last_play_time, splatoon, game_sp_id)

    except Exception as ex:
        cron_logger.warning(f'set_user_report_task error: {msg_id}, {ex}')


async def set_user_report(u, res_summary, res_coop, last_play_time, splatoon, player_code):
    """写用户日报数据"""
    # 总对战数目
    all_data = await splatoon.get_total_query()

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
        'user_id': u.id,
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
        model_add_report(**_report)


async def send_report_task():
    """8点时进行发信"""
    cron_logger.info(f'create_send_report_tasks start')
    t = dt.utcnow()

    users = model_get_all_user()
    for user in users:
        # 排除qq平台发信 和 日报通知未打开的用户
        if user.platform == "QQ" or not user.report_notify:
            continue
        # 每次循环强制睡眠0.5s，使一分钟内最多触发120次发信，避免超出阈值
        time.sleep(0.5)
        try:
            msg = get_report(user.platform, user.user_id)
            if msg:
                await notify_to_private(user.platform, user.user_id, msg)
        except Exception as e:
            cron_logger.warning(f'create_send_report_tasks error: {e}')
            continue

    cron_logger.info(f'create_send_report_tasks end: {dt.utcnow() - t}')