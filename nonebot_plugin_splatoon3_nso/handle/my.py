import json
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime as dt, timedelta
from pathlib import Path

import unicodedata
from nonebot import on_keyword

from .send_msg import bot_send, bot_send_more_nso_help_md, bot_mixed_send
from .utils import _check_session_handler
from ..config import plugin_config
from ..data.data_source import dict_get_or_set_user_info, model_get_temp_image_path, model_get_or_set_user, \
    model_get_power_rank, model_set_user_friend, model_get_another_account_user, global_user_info_dict, \
    model_get_all_top_all
from ..data.utils import GlobalUserInfo
from ..s3s.iksm import F_GEN_URL
from ..s3s.splatoon import Splatoon
from ..s3s.stat import STAT, CONFIG_DATA
from ..utils import get_msg_id, convert_td
from ..utils.bot import *
from ..utils.redis import api_rset_json_file_name, api_rset_info
from ..utils.utils import DIR_RESOURCE, get_jwt_exp_info, game_name_replace

MSG_PRIVATE = "该指令需要私信机器人才能使用"
NSO_WEB_CACHE_DICT = {}


@on_command("me", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def me(bot: Bot, event: Event):
    """查询 我的"""
    await bot_send(bot, event, message="请求个人数据中，请稍等...")

    from_group = False
    if isinstance(event, All_Group_Message):
        from_group = True

    msg = await get_me(bot, event, from_group)

    text_start = f"以下是喷3个人总览数据"
    await bot_mixed_send(bot, event, msg, image_width=450, text_start=text_start)


async def get_me(bot, event, from_group):
    """获取我的各种信息"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    history_summary = await splatoon.get_history_summary()
    if not history_summary:
        history_summary = await splatoon.get_history_summary(multiple=True)
    total_query = await splatoon.get_total_query(multiple=True)
    if not total_query:
        total_query = await splatoon.get_total_query(multiple=True)
    coop = await splatoon.get_coops(multiple=True)
    if not coop:
        coop = await splatoon.get_coops(multiple=True)
    weapons = await splatoon.get_weapons(multiple=True)
    if not weapons:
        weapons = await splatoon.get_weapons(multiple=True)

    try:
        msg = await get_me_md(user, history_summary, total_query, coop, weapons, from_group)
    except Exception as e:
        logger.error(f"get_me md error:{e}")
        msg = f"获取数据失败，请稍后再试"
    return msg


async def get_me_md(user: GlobalUserInfo, summary, total, coops, weapons, from_group=False):
    """获取 我的 md文本"""
    player = summary['data']['currentPlayer']
    history = summary['data']['playHistory']
    start_time = history['gameStartTime']
    s_time = dt.strptime(start_time, '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=8)
    c_time = dt.strptime(history['currentTime'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=8)

    all_cnt = ''
    r = ''
    if total:
        total_cnt = total['data']['playHistory']['battleNumTotal']
        all_cnt = f"/{total_cnt}"
        if total_cnt:
            r = f"{history['winCountTotal'] / total_cnt:.2%}"

    def get_best_weapons_list(__weapons: list[dict], __type: str):
        w_lst = weapons['data']['weaponRecords']['nodes']
        __w_l = []
        for w in w_lst:
            if not w.get('stats'):
                continue
            stats = w.get('stats')
            if not stats.get(__type):
                continue
            __w_l.append({'weapon_id': w.get('weaponId'),
                          'weapon_name': w.get('name'),
                          'power': stats.get('maxWeaponPower', 0),
                          'win': stats.get('win', 0),
                          })
        return __w_l

    # 全部有分数的武器 以及 常用武器(赢100局武器的前三名)
    weapons_str = ''
    best_weapon = ''
    if weapons and not from_group:
        w_l_1 = get_best_weapons_list(weapons, __type="maxWeaponPower")
        if w_l_1:
            w_power_l = sorted(w_l_1, key=lambda x: x['power'], reverse=True)
            weapons_str = '|武器分数top5|'
            new_weapons_str_list = []
            for w in w_power_l[:5]:
                ww_img = await model_get_temp_image_path('battle_weapon_main', w['weapon_name'])
                ww_img = f'''<img style='height:30px; width:auto' src="{ww_img}"/>'''
                new_weapons_str_list.append(f"{ww_img} &nbsp;&nbsp;{w['power']:.2f}")
            weapons_str += '<br>'.join(new_weapons_str_list)
            weapons_str += '|'
    if weapons:
        w_l_2 = get_best_weapons_list(weapons, __type="win")
        if w_l_2:
            w_win_l = sorted(w_l_2, key=lambda x: x['win'], reverse=True)
            for w in w_win_l[:3]:
                if w["win"] > 100:
                    ww_img = await model_get_temp_image_path('battle_weapon_main', w['weapon_name'])
                    best_weapon += f'<img height="22" src="{ww_img}"/>({w["win"]}胜)&nbsp;&nbsp;'
        if best_weapon:
            best_weapon = f'|常用武器| {best_weapon}|'

    coop_msg = ''
    if coops:
        coops = coops['data']['coopResult']
        card = coops['pointCard']
        p = coops['scale']
        level = f"{coops['regularGrade']['name']} {coops['regularGradePoint']}"
        boss_per_cnt = ''
        if card['defeatBossCount']:
            boss_per_cnt = f"({card['playCount'] / card['defeatBossCount']:.2f})"
        gdpc = ''
        dpc = ''
        rpc = ''
        ppc = ''
        if card['playCount']:
            gdpc = f"({card['goldenDeliverCount'] / card['playCount']:.2f})"
            dpc = f"({card['deliverCount'] / card['playCount']:.2f})"
            rpc = f"({card['rescueCount'] / card['playCount']:.2f})"
            ppc = f"({card['totalPoint'] / card['playCount']:.2f})"
        if from_group:
            coop_msg = f"""|当前打工段位|{level}|
|打工次数|{card['playCount']}|
|头目鲑鱼|{card['defeatBossCount']} {boss_per_cnt}|
|鳞片|🏅️{p['gold']} 🥈{p['silver']} 🥉{p['bronze']}|"""
        else:
            coop_msg = f"""|当前打工段位|{level}|
|现有点数|{card['regularPoint']}|
|打工次数|{card['playCount']}|
|金鲑鱼卵|{card['goldenDeliverCount']} {gdpc}|
|鲑鱼卵|{card['deliverCount']} {dpc}|
|头目鲑鱼|{card['defeatBossCount']} {boss_per_cnt}|
|救援次数|{card['rescueCount']} {rpc}|
|累计点数|{card['totalPoint']} {ppc}|
|鳞片|🏅️{p['gold']} 🥈{p['silver']} 🥉{p['bronze']}|"""

    # 最高power
    ar_max_power = (history.get('xMatchMaxAr') or {}).get('power') or 0  # 区域
    lf_max_power = (history.get('xMatchMaxLf') or {}).get('power') or 0  # 塔楼
    gl_max_power = (history.get('xMatchMaxGl') or {}).get('power') or 0  # 鱼虎
    cl_max_power = (history.get('xMatchMaxCl') or {}).get('power') or 0  # 蛤蜊
    # 最高排名
    ar_max_rank = (history.get('xMatchMaxAr') or {}).get('rank') or 0  # 区域
    lf_max_rank = (history.get('xMatchMaxLf') or {}).get('rank') or 0  # 塔楼
    gl_max_rank = (history.get('xMatchMaxGl') or {}).get('rank') or 0  # 鱼虎
    cl_max_rank = (history.get('xMatchMaxCl') or {}).get('rank') or 0  # 蛤蜊
    # 当前排名
    ar_rank = (history.get('xMatchRankAr') or 0)  # 区域
    lf_rank = (history.get('xMatchRankLf') or 0)  # 塔楼
    gl_rank = (history.get('xMatchRankGl') or 0)  # 鱼虎
    cl_rank = (history.get('xMatchRankCl') or 0)  # 蛤蜊
    # X赛最高战力
    x_max_power_msg = ''
    if any([ar_max_power, lf_max_power, gl_max_power, cl_max_power]) and not from_group:
        # 1. 构建维度名称与分数的映射字典，方便后续查找最大值
        power_dict = {
            '区域': ar_max_power,
            '塔楼': lf_max_power,
            '鱼虎': gl_max_power,
            '蛤蜊': cl_max_power
        }
        # 2. 找出最大值对应的维度名称（如果多个维度值相同且都是最大值，取第一个）
        max_power = max([v for v in power_dict.values() if v])
        max_power_key = next((key for key, value in power_dict.items() if value == max_power), None)
        # 3. 逐个构建每个维度的文本，最大值维度添加红色样式
        parts = []
        # 第一行：区域 + 塔楼
        ar_text = f'<span style="color:red">区域:{ar_max_power:>7.2f}</span>' if '区域' == max_power_key else f'区域:{ar_max_power:>7.2f}'
        lf_text = f'<span style="color:red">塔楼:{lf_max_power:>7.2f}</span>' if '塔楼' == max_power_key else f'塔楼:{lf_max_power:>7.2f}'
        parts.append(f'{ar_text}, {lf_text}<br>')
        # 第二行：鱼虎 + 蛤蜊
        gl_text = f'<span style="color:red">鱼虎:{gl_max_power:>7.2f}</span>' if '鱼虎' == max_power_key else f'鱼虎:{gl_max_power:>7.2f}'
        cl_text = f'<span style="color:red">蛤蜊:{cl_max_power:>7.2f}</span>' if '蛤蜊' == max_power_key else f'蛤蜊:{cl_max_power:>7.2f}'
        parts.append(f' {gl_text}, {cl_text}')

        # 4. 拼接最终文本
        x_max_power_msg = f"|X最高战力|{''.join(parts)}|"
    # X赛最高排名
    x_max_rank_msg = ''
    if any([ar_max_rank, lf_max_rank, gl_max_rank, cl_max_rank]) and not from_group:
        # 1. 构建维度名称与分数的映射字典，方便后续查找最大值
        rank_dict = {
            '区域': ar_max_rank,
            '塔楼': lf_max_rank,
            '鱼虎': gl_max_rank,
            '蛤蜊': cl_max_rank
        }
        # 2. 找出最小排名
        min_rank = min([v for v in rank_dict.values() if v])
        min_rank_key = next((key for key, value in rank_dict.items() if value == min_rank), None)
        # 3. 逐个构建每个维度的文本，最小排名添加红色样式
        parts = []
        # 第一行：区域 + 塔楼
        ar_text = f'<span style="color:red">区域:{ar_max_rank}名</span>' if '区域' == min_rank_key else f'区域:{ar_max_rank}名'
        lf_text = f'<span style="color:red">塔楼:{lf_max_rank}名</span>' if '塔楼' == min_rank_key else f'塔楼:{lf_max_rank}名'
        parts.append(f'{ar_text}, {lf_text}<br>')
        # 第二行：鱼虎 + 蛤蜊
        gl_text = f'<span style="color:red">鱼虎:{gl_max_rank}名</span>' if '鱼虎' == min_rank_key else f'鱼虎:{gl_max_rank}名'
        cl_text = f'<span style="color:red">蛤蜊:{cl_max_rank}名</span>' if '蛤蜊' == min_rank_key else f'蛤蜊:{cl_max_rank}名'
        parts.append(f' {gl_text}, {cl_text}')

        # 4. 拼接最终文本
        x_max_rank_msg = f"|X最高排名|{''.join(parts)}|"
    # X赛当前排名
    x_now_rank_msg = ''
    if any([ar_rank, lf_rank, gl_rank, cl_rank]) and not from_group:
        # 1. 构建维度名称与分数的映射字典，方便后续查找最大值
        now_rank_dict = {
            '区域': ar_rank,
            '塔楼': lf_rank,
            '鱼虎': gl_rank,
            '蛤蜊': cl_rank
        }
        # 2. 找出最小排名
        min_now_rank = min([v for v in now_rank_dict.values() if v])
        min_now_rank_key = next((key for key, value in now_rank_dict.items() if value == min_now_rank), None)
        # 3. 逐个构建每个维度的文本，最小排名添加红色样式
        parts = []
        # 第一行：区域 + 塔楼
        ar_text = f'<span style="color:red">区域:{ar_rank}名</span>' if '区域' == min_now_rank_key else f'区域:{ar_rank}名'
        lf_text = f'<span style="color:red">塔楼:{lf_rank}名</span>' if '塔楼' == min_now_rank_key else f'塔楼:{lf_rank}名'
        parts.append(f'{ar_text}, {lf_text}<br>')
        # 第二行：鱼虎 + 蛤蜊
        gl_text = f'<span style="color:red">鱼虎:{gl_rank}名</span>' if '鱼虎' == min_now_rank_key else f'鱼虎:{gl_rank}名'
        cl_text = f'<span style="color:red">蛤蜊:{cl_rank}名</span>' if '蛤蜊' == min_now_rank_key else f'蛤蜊:{cl_rank}名'
        parts.append(f' {gl_text}, {cl_text}')

        # 4. 拼接最终文本
        x_now_rank_msg = f"|X当前排名|{''.join(parts)}|"

    # X最高战力bot排名
    x_power_rank_msg = ''
    if any([ar_max_power, lf_max_power, gl_max_power, cl_max_power]):
        _dict_rank = model_get_power_rank()
        _rank = _dict_rank.get(user.game_sp_id)
        if _rank:
            x_power_rank_msg = f"|X最高战力bot排名|{_rank}名|"

    _league = ''
    _open = ''
    if history.get('leagueMatchPlayHistory'):
        _l = history['leagueMatchPlayHistory']
        _n = _l['attend'] - _l['gold'] - _l['silver'] - _l['bronze']
        _league = f"🏅️{_l['gold']:>3} 🥈{_l['silver']:>3} 🥉{_l['bronze']:>3} &nbsp; ♉︎{_n:>3} (总{_l['attend']})"
    if history.get('bankaraMatchOpenPlayHistory'):
        _o = history['bankaraMatchOpenPlayHistory']
        _n = _o['attend'] - _o['gold'] - _o['silver'] - _o['bronze']
        _open = f"🏅️{_o['gold']:>3} 🥈{_o['silver']:>3} 🥉{_o['bronze']:>3} &nbsp; ♉︎{_n:>3} (总{_o['attend']})"

    player_name = game_name_replace(player['name'])
    name_id = player['nameId']
    user_name = f'{player_name} #{name_id}'

    icon_img = ""
    if user.nsa_id:
        icon_img = await model_get_temp_image_path('my_icon_by_nsa_id', user.nsa_id, player['userIcon']['url'])
    else:
        # 我的头像，优先使用sp_id进行储存，没有就用play_name-code
        icon_img = await model_get_temp_image_path('my_icon', user.game_sp_id or f'{player_name}_{name_id}',
                                                   player['userIcon']['url'])

    img = f'''<img height='30px' style='position:absolute;margin-left:-30px;margin-top:-15px' src="{icon_img}"/>'''

    weapon_img = await model_get_temp_image_path('battle_weapon_main',
                                                 player['weapon']['name'],
                                                 player['weapon']['image']['url'])
    w_img = f'''<img height='30px' style='position:absolute;margin-left:-30px;margin-top:-15px' src="{weapon_img}"/>'''

    badges_str = ''
    _idx = 1
    for b in (player.get('nameplate') or {}).get('badges') or []:
        if b:
            _b_id = b.get('id')
            _b_url = (b.get('image') or {}).get('url')
            if _b_url:
                b_img = await model_get_temp_image_path('user_nameplate_badge', _b_id, _b_url)
                _style = f'position:absolute;margin-top:-4px;margin-left:{_idx * 30}px'
                badges_str += f'''<img height='30px' style='{_style}' src="{b_img}"/>'''
        _idx += 1

    # 构建主表格
    msg = f"""####
|--------------|---|
|{w_img}|{user_name}|
|{img}|{player['byname']}|
|等级|{history['rank']} {badges_str}|
|技术|{history['udemae']}/最高{history['udemaeMax']}|
|总胜利数|{history['winCountTotal']}{all_cnt} {r}|
|涂墨面积|{history['paintPointTotal']:,}p|
|徽章|{len(history['badges'])} {best_weapon}|
|活动|{_league}|
|开放|{_open}|
|首次游玩|{s_time:%Y-%m-%d %H:%M:%S} +08:00|
|当前时间|{c_time:%Y-%m-%d %H:%M:%S} +08:00|
"""

    # 添加X赛相关数据
    if x_max_power_msg:
        msg += x_max_power_msg + "\n"
    if x_max_rank_msg:
        msg += x_max_rank_msg + "\n"
    if x_now_rank_msg:
        msg += x_now_rank_msg + "\n"
    if x_power_rank_msg:
        msg += x_power_rank_msg + "\n"

    # 添加武器分数
    if weapons_str:
        msg += weapons_str + "\n"

    # 添加打工数据
    if coop_msg:
        msg += "\n" + coop_msg + "\n"
    # 添加上榜记录
    top_res = model_get_all_top_all(user.game_sp_id)
    if top_res:
        msg += f"|上榜记录|{len(top_res)}次 &nbsp;&nbsp; /top 查询排行榜|\n"

    # 添加提示信息
    if any([ar_max_power, lf_max_power, gl_max_power, cl_max_power]) and from_group:
        msg += f"\nTips：私聊使用/me 查询时会额外展示X分和武器分\n"

    return msg


@on_command("friends", aliases={'friend', 'fr'}, priority=10, block=True).handle(
    parameterless=[Depends(_check_session_handler)])
async def friends(bot: Bot, event: Event):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg = await get_friends_md(splatoon)

    text_start = f"以下是喷3好友的在线情况数据"
    await bot_mixed_send(bot, event, msg, image_width=600, text_start=text_start)


async def get_friends_md(splatoon, lang='zh-CN'):
    res = await splatoon.get_friends()
    if not res:
        return 'bot网络错误，请稍后再试.'

    msg = f'''#### 在线好友 HKT {dt.now():%Y-%m-%d %H:%M:%S}
||||||
|---:|---|:---|:---|---|
|ns好友名|ns头像|sp3好友名|状态|数量|
'''
    _dict = defaultdict(int)
    for f in res['data']['friends']['nodes']:
        if f.get('onlineState') == 'OFFLINE':
            continue
        _state = fmt_sp3_state(f)
        _state = get_cn_sp3_stat(_state)

        _dict[_state] += 1
        n = f['playerName'] or f.get('nickname')
        n = game_name_replace(n)

        img_type = "friend_icon"
        # 储存名使用friend_id
        icon_img = await model_get_temp_image_path(img_type, f['id'], f['userIcon']['url'])
        img = f'''<img height="40" src="{icon_img}"/>'''
        if f['playerName'] and f['playerName'] != f['nickname']:
            nickname = game_name_replace(f['nickname'])
            n = f'{f["playerName"]}|{img}|{nickname}'
        else:
            n = f'{n}|{img}|'
        msg += f'''|{n}| {_state}|\n'''

        # 写入好友数据库
        friend_id = f['id']
        player_name = f.get('playerName') or ''
        nickname = f.get('nickname') or ''
        user_icon = f['userIcon']['url']
        model_set_user_friend([(splatoon.user_id, friend_id, player_name, nickname, user_icon)])

    msg += '||\n'
    _dict['TOTAL'] = sum(_dict.values())
    for k, v in _dict.items():
        msg += f'||||{k}| {v}|\n'
    msg += '||\n'
    return msg


nsfr = on_command("ns_friends", aliases={'ns_friend', 'ns_fr', 'nsfr'}, priority=10, block=True)


@nsfr.handle(
    parameterless=[Depends(_check_session_handler)])
async def ns_friends(bot: Bot, event: Event):
    """获取ns好友"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg = await get_ns_friends_md(splatoon)

    text_start = f"以下是ns好友的在线情况数据"
    await bot_mixed_send(bot, event, msg, image_width=680, text_start=text_start)


async def get_ns_friends_md(splatoon: Splatoon):
    """获取ns好友md"""
    msg_id = get_msg_id(splatoon.platform, splatoon.user_id)
    try:
        res = await splatoon.app_ns_friend_list()
        if not res:
            res = await splatoon.app_ns_friend_list()
    except Exception as e:
        logger.error(f"{msg_id} get ns_friends error:{e}")
        msg = "bot网络错误，请稍后再试"
        return msg

    if not res:
        logger.error(f"{msg_id} get ns_friends error")
        msg = "bot网络错误，请稍后再试"
        return msg
    res = res.get('result')

    get_sp3 = False

    for f in res.get('friends') or []:
        if (f.get('presence') or {}).get('state') != 'ONLINE':
            continue
        if f['presence']['game'].get('name') == 'Splatoon 3':
            get_sp3 = True
            break

    dict_sp3 = {}
    _dict_sp3 = defaultdict(int)
    if get_sp3:
        sp3_res = await splatoon.get_friends()
        if sp3_res:
            for f in sp3_res['data']['friends']['nodes']:
                if f.get('onlineState') == 'OFFLINE':
                    continue
                _state = fmt_sp3_state(f)
                if _state == 'ONLINE':
                    continue
                _state = get_cn_sp3_stat(_state)
                dict_sp3[f.get('nickname')] = _state
                _dict_sp3[_state] += 1

    msg = f'''#### NS在线好友 HKT {dt.now():%Y-%m-%d %H:%M:%S}
|||||
|---:|---|---|:---|
|ns好友名|ns头像|游戏名|数量|
'''
    _dict = defaultdict(int)
    for f in res.get('friends') or []:
        if (f.get('presence') or {}).get('state') != 'ONLINE' and f.get('isFavoriteFriend') is False:
            continue
        u_name = f.get('name') or ''
        u_name = game_name_replace(u_name)
        u_name_note = f.get('note') or ''
        u_name_note = game_name_replace(u_name_note)
        if u_name_note:
            u_name += f"<br>备注:{u_name_note}"

        img_type = "ns_friend_icon"
        # 储存名使用friend_id
        icon_img = await model_get_temp_image_path(img_type, f['nsaId'], f['imageUri'])
        img_str = f'''<img height="40" src="{icon_img}"/>'''
        msg += f'|{u_name}|{img_str}'
        if (f.get('presence') or {}).get('state') == 'ONLINE':
            _game_name = f['presence']['game'].get('name') or ''
            _game_name = _game_name.replace('The Legend of Zelda: Tears of the Kingdom', 'TOTK')
            _game_name = _game_name.replace("Nintendo Switch 2 Edition", "ns2增强版")
            msg += f"|{_game_name}"
            _dict[_game_name] += 1
            if f['presence']['game'].get('totalPlayTime'):
                msg += f"({int(f['presence']['game'].get('totalPlayTime') / 60)}h)|"
            else:
                msg += '|'
            if f.get('name') in dict_sp3:
                msg += f" {dict_sp3[f.get('name')]}|"
            else:
                msg += '|'
        else:
            t = (f.get('presence') or {}).get('logoutAt') or 0
            if t:
                delt = str(dt.utcnow() - dt.utcfromtimestamp(t))
                tt = delt
                if tt.startswith('0'):
                    tt = tt.split(', ')[-1]
                tt = tt.split('.')[0][:-3].replace(':', 'h')
                msg += f" |(offline about {tt})||"
            else:
                msg += f" |({(f.get('presence') or {}).get('state', 'offline')})||"
        msg += '\n'
    st = ''
    _dict['total online'] = sum(_dict.values())
    _dict['total'] = len(res.get('friends') or [])
    for k, v in _dict.items():
        st += f'|||{k}| {v}|\n'

    if _dict_sp3:
        _dict_sp3['total sp3'] = sum(_dict_sp3.values())
        st += '|||||\n'
        for k, v in _dict_sp3.items():
            st += f'|||{k}| {v}|\n'

    msg = f'''
{msg}|||||
{st}
'''
    return msg


matcher_fc = on_command("friend_code", aliases={'friends_code', 'fc'}, priority=10, block=True)


@matcher_fc.handle(parameterless=[Depends(_check_session_handler)])
async def friend_code(bot: Bot, event: Event, args: Message = CommandArg()):
    """获取ns 好友码"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    force = False  # 强制从接口获取
    msg_id = get_msg_id(platform, user_id)

    if "force" in args.extract_plain_text():
        force = True
    msg = ""
    if user and user.ns_friend_code and not force:
        msg += f"ns用户名: {user.ns_name}\n好友码(sw码): SW-{user.ns_friend_code}"
    else:
        splatoon = Splatoon(bot, event, user)
        res = {}
        try:
            res = await splatoon.app_ns_myself() or {}
        except Exception as e:
            logger.error(f"{msg_id} get friend_code error:{e}")
            msg = "bot网络错误，请稍后再试"

        name = res.get('name')
        code = res.get('code')
        icon = res.get('icon')
        if user.nsa_id:
            my_icon = await model_get_temp_image_path('my_icon_by_nsa_id', user.nsa_id, icon)
        elif user.game_sp_id:
            my_icon = await model_get_temp_image_path('my_icon', user.game_sp_id, icon)
        if code:
            dict_get_or_set_user_info(platform, user_id, ns_name=name, ns_friend_code=code)
            msg += f"已更新新好友码并缓存\n"
            msg += f"ns用户名: {res.get('name')}\n好友码(sw码): SW-{user.ns_friend_code}"

    await bot_send(bot, event, msg)


def fmt_sp3_state(f):
    """sp3好友状态格式化"""
    _state = f.get('onlineState')
    if _state == 'OFFLINE':
        return

    if _state == 'VS_MODE_FIGHTING':
        _state = f'VS_MODE ({f["vsMode"]["mode"]})'
        if f['vsMode']['mode'] == 'BANKARA':
            if f['vsMode']['id'] == 'VnNNb2RlLTUx':
                _state += 'O'
            else:
                _state += 'C'

        elif f['vsMode']['mode'] == 'FEST':
            mod_id = f['vsMode']['id']
            if mod_id == 'VnNNb2RlLTY=':
                _state += 'O'
            elif mod_id == 'VnNNb2RlLTg=':
                _state += '3'
            else:
                _state += 'C'

    elif _state == 'COOP_MODE_FIGHTING':
        _state = f'COOP_MODE'
        if f.get('coopRule') != 'REGULAR':
            _state += f" ({f.get('coopRule')})"
    return _state


def wide_chars(s):
    """return the extra width for wide characters
    ref: http://stackoverflow.com/a/23320535/1276501"""
    return sum(unicodedata.east_asian_width(x) in ('F', 'W') for x in s)


def get_cn_sp3_stat(_st):
    """获取用户状态的中文翻译"""
    if "PRIVATE" in _st:
        _st = "私房"
    elif "X_MATCH)" in _st:
        _st = "X比赛"
    elif "RA)O" in _st:
        _st = "开放"
    elif "RA)C" in _st:
        _st = "挑战"
    elif "MATCHING" in _st:
        _st = "匹配中"
    elif "COOP" in _st:
        _st = "打工"
    elif "REGULAR)" in _st:
        _st = "涂地"
    elif _st == "ONLINE":
        _st = "在线"
    elif "LEAGUE" in _st:
        _st = "活动"
    elif "FEST)O" in _st:
        _st = "祭典开放"
    elif "FEST)C" in _st:
        _st = "祭典挑战"
    elif "FEST)3" in _st:
        _st = "祭典三色"
    return _st


@on_command("report_notify", block=True).handle(parameterless=[Depends(_check_session_handler)])
async def report_notify(bot: Bot, event: Event, args: Message = CommandArg()):
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, "QQ平台暂不支持本功能")
        return
    cmd = args.extract_plain_text().strip()
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg = f'```\n'
    if cmd == "open":
        user = dict_get_or_set_user_info(platform, user_id, report_notify=1)
        msg += "日报 已开启每日主动推送，将会在每日早8点推送过去一天内战绩变化情况，您也可通过主动查询命令/report 进行查询\n"
    elif cmd == "close":
        user = dict_get_or_set_user_info(platform, user_id, report_notify=0)
        msg += "日报 已关闭每日主动推送，日报数据仍会定时进行更新，您可通过主动查询命令/report 进行查询\n\n"
    msg += f'/report_notify open 开启每日日报推送\n/report_notify close 关闭每日日报推送\n'
    msg += f'```'
    await bot_send(bot, event, message=msg)


@on_command("stat_notify", aliases={'api_notify'}, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def stat_notify(bot: Bot, event: Event, args: Message = CommandArg()):
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, "QQ平台暂不支持本功能")
        return
    cmd = args.extract_plain_text().strip()
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg = f'```\n'
    if cmd == "open":
        user = dict_get_or_set_user_info(platform, user_id, stat_notify=1)
        msg += "stat.ink同步情况 已开启主动推送，每2h将进行一次同步\n"
    elif cmd == "close":
        user = dict_get_or_set_user_info(platform, user_id, stat_notify=0)
        msg += "stat.ink同步情况 已关闭主动推送，后台仍会2h进行一次同步\n\n"
    msg += f'/stat_notify open 开启stat.ink同步情况推送\n/stat_notify close 关闭stat.ink同步情况推送\n/sync_now 手动发起同步请求\n'
    msg += f'```'
    await bot_send(bot, event, message=msg)


@on_command("my_icon", aliases={'myicon'}, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def my_icon(bot: Bot, event: Event, args: Message = CommandArg()):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    force = False  # 强制从接口获取
    msg_id = get_msg_id(platform, user_id)

    if "force" in args.extract_plain_text():
        force = True
    msg = ""
    msg_error = "本地未缓存nso头像，请在使用一次/last 命令进行缓存后重试"
    my_icon_path = ""

    if (user.nsa_id or user.game_sp_id) and not force:
        my_icon_path = (await model_get_temp_image_path('my_icon_by_nsa_id', user.nsa_id) or
                        await model_get_temp_image_path('my_icon', user.game_sp_id))
    else:
        splatoon = Splatoon(bot, event, user)
        res = {}
        try:
            res = await splatoon.app_ns_myself() or {}
        except Exception as e:
            logger.error(f"{msg_id} get my_icon error:{e}")
            msg = "bot网络错误，请稍后再试"

        icon = res.get('icon')
        if user.nsa_id:
            my_icon_path = await model_get_temp_image_path('my_icon_by_nsa_id', user.nsa_id, icon)
        elif user.game_sp_id:
            my_icon_path = await model_get_temp_image_path('my_icon', user.game_sp_id, icon)

    if my_icon_path:
        with open(my_icon_path, "rb") as f:
            _my_icon = f.read()
            msg = _my_icon
    else:
        msg = msg_error

    text_start = f"以下是你的ns头像"
    await bot_mixed_send(bot, event, message=msg, text_start=text_start)


@on_keyword({"我已知晓nso查询使用了第三方接口的风险并重新启用nso查询"}, block=True).handle()
async def re_enable(bot: Bot, event: Event):
    """同意条款重新启用nso查询"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = model_get_or_set_user(platform, user_id)
    if user:
        # 更新协议状态
        user = dict_get_or_set_user_info(platform, user_id, user_agreement=1)
        msg = "nso功能已重新启用，您可以继续使用/last 等nso查询命令"
        await bot_send(bot, event, message=msg)
        users = model_get_another_account_user(platform, user_id)
        if len(users) > 0:
            for u in users:
                # 如果存在全局缓存，也更新缓存数据
                key = get_msg_id(u.platform, u.user_id)
                user_info = global_user_info_dict.get(key)
                if user_info:
                    # 更新缓存数据
                    dict_get_or_set_user_info(u.platform, u.user_id, user_agreement=1)
                else:
                    # 更新数据库数据
                    model_get_or_set_user(u.platform, u.user_id, user_agreement=1)


@on_command("观星导出", block=True).handle(parameterless=[Depends(_check_session_handler)])
async def seed_export(bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    net_error_msg = "bot网络错误，请稍后再试"
    if isinstance(event, All_Group_Message):
        await matcher.finish(MSG_PRIVATE)

    msg_id = get_msg_id(platform, user_id)
    user = dict_get_or_set_user_info(platform, user_id)
    if user and user.export_seed:
        await matcher.finish("正在导出观星文件中，请勿重复触发")
    if not user.game_sp_id:
        no_sp_id_msg = "请先使用一次/last命令后再使用观星导出"
        await matcher.finish(no_sp_id_msg)

    user = dict_get_or_set_user_info(platform, user_id, export_seed=1)  # 设置为正在导出
    # 用户等待提示词
    if isinstance(bot, QQ_Bot):
        msg1 = (
            f"观星网站需要上传一个装备的json文件，QQ平台bot无法发送任何文件，请访问教程网址\n\nblog.ayano.top/archives/525/ \n\n,"
            f"输入接下来发给你的观星访问密钥来下载观星json文件\n\n正在生成观星访问密钥中(大约需要两分钟)，请稍后。。。")
        if isinstance(bot, QQ_Bot):
            msg1 = msg1.replace(".", "点")
        await bot_send(bot, event, message=msg1, skip_ad=True)
    else:
        await bot_send(bot, event, message="正在导出观星json文件(大约需要两分钟)，请稍等。。。", skip_ad=True)

    try:
        # 生成观星文件
        splatoon = Splatoon(bot, event, user)
        ok = await splatoon.test_page()
        if not ok:
            await matcher.finish(net_error_msg)
        config_data = CONFIG_DATA(
            f_gen=F_GEN_URL,
            user_lang='zh-CN',
            user_country='JP',
            stat_key=user.stat_key,
            g_token=splatoon.g_token,
            bullet_token=splatoon.bullet_token,
            session_token=splatoon.session_token
        )
        stat = STAT(splatoon=splatoon, config_data=config_data)
        try:
            export_data: dict = await stat.export_seed_json(game_sp_id=user.game_sp_id)
        except Exception as e:
            logger.error(f"观星导出 error:{e}")
            msg = f"获取观星json文件失败，请稍后再试"
            await matcher.finish(msg)

        file_name = export_data.get("file_name")
        json_bytes = export_data.get("json_bytes")
        if isinstance(bot, QQ_Bot):
            msg2 = f"观星访问密钥获取成功，请将密钥输入到上面教程网址下载观星json文件，以下是您的观星访问密钥，请勿外泄，该一次性密钥有效期为2h"
            await bot_send(bot, event, message=msg2, skip_ad=True)
            # 生成密钥
            secret_code = secrets.token_urlsafe(6)  # 6字节，长度为8位
            # 生成本地缓存文件
            file_dir = os.path.join(DIR_RESOURCE, "temp_seedchecker_file")
            file_path = os.path.join(file_dir, file_name)
            os.makedirs(file_dir, exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(json_bytes)
            # 将文件名和随机密钥写redis
            await api_rset_json_file_name(secret_code, file_name)
            msg3 = f"xyy-seedchecker-{secret_code}"  # 16+8 = 24位密钥
            await bot_send(bot, event, message=msg3, skip_ad=True)
        else:
            await bot_send(bot, event, message=json_bytes, file_name=file_name, skip_ad=True)
            msg2 = f"观星json文件导出成功，请参照网址\n\nblog.ayano.top/archives/525/ \n\n的教程进行后续操作"
            await bot_send(bot, event, message=msg2, skip_ad=True)
    finally:
        user = dict_get_or_set_user_info(platform, user_id, export_seed=0)  # 取消导出状态


@on_command("nso_web", aliases={'nso网页版', 'nsoweb'}, block=True).handle(
    parameterless=[Depends(_check_session_handler)])
async def nso_web(bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    net_error_msg = "bot网络错误，请稍后再试"
    if isinstance(event, All_Group_Message):
        await matcher.finish(MSG_PRIVATE)

    user = dict_get_or_set_user_info(platform, user_id)
    msg_id = get_msg_id(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg1 = ("以下导出的nso网页版访问密钥可以让你在电脑网页上查看并操作nso里面的喷三'鱿鱼圈'应用，当你在网络不好登不上nso，"
            "或者更新不了nso最新版本时可以派上用场\n\n正在生成nso网页版访问密钥中，请稍等。。。")
    if isinstance(bot, QQ_Bot):
        msg1 = msg1.replace(".", "点")
    await bot_send(bot, event, message=msg1, skip_ad=True)
    # 判断是否存在仍然有效的token
    nso_web_data = NSO_WEB_CACHE_DICT.get(msg_id)
    now = time.time()
    need_refresh = True
    remaining_seconds = 0
    if nso_web_data:
        ex_time = nso_web_data.get("ex_time")
        if ex_time:
            remaining_seconds = int(ex_time) - int(now)
            if remaining_seconds >= 1800:
                # 如果剩余时间大于1800秒(30分钟)，将缓存的密钥重新返回给用户，不进行刷新
                need_refresh = False
    if not need_refresh:
        # 存在有效的gtoken缓存
        msg2 = f"存在仍有效的nso网页版访问密钥，请参照网址\n\nblog.ayano.top/archives/567/ \n\n的教程进行后续操作，以下是您的nso网页版访问密钥，请勿外泄，该凭证有效期剩余 {convert_td(timedelta(seconds=remaining_seconds))}"
        if isinstance(bot, QQ_Bot):
            msg2 = msg2.replace(".", "点")
        await bot_send(bot, event, message=msg2, skip_ad=True)
        secret_code = nso_web_data.get('secret_code')
        msg3 = f"xyy-nsoweb-{secret_code}"
        await bot_send(bot, event, message=msg3, skip_ad=True)
    else:
        # 强制刷新token延长bullet_token时间
        ok = await splatoon.refresh_gtoken_and_bullettoken(skip_access=False)
        if not ok:
            await matcher.finish(net_error_msg)
        msg2 = f"nso网页版访问密钥获取成功，请参照网址\n\nblog.ayano.top/archives/567/ \n\n的教程进行后续操作，以下是您的访问密钥，请勿外泄，该凭证有效期为 3h"
        if isinstance(bot, QQ_Bot):
            msg2 = msg2.replace(".", "点")
        await bot_send(bot, event, message=msg2, skip_ad=True)
        g_token = splatoon.g_token
        # 校验gtoken并计算剩余时间
        jwt_info = get_jwt_exp_info(g_token)
        exp_ts = jwt_info.get("exp_ts")
        ## 生成密钥
        secret_code = secrets.token_urlsafe(6)  # 6字节，长度为8位
        d = {
            "platform": platform,
            "user_id": user_id,
            "msg_id": msg_id,
            "game_sp_id": user.game_sp_id or "",
            "gtoken": splatoon.g_token,
            "ex_time": exp_ts,  # 过期的时间戳，
            "secret_code": secret_code
        }
        # 将用户信息和随机密钥写redis
        await api_rset_info(secret_code, d)
        # 同时将msg_id作为key写到缓存字典
        NSO_WEB_CACHE_DICT[msg_id] = d
        msg3 = f"xyy-nsoweb-{secret_code}"
        await bot_send(bot, event, message=msg3, skip_ad=True)


@on_command("更多nso指令", block=True).handle()
async def more_nso_help(bot: Bot, event: Event, args: Message = CommandArg()):
    """发送更多nso帮助的二级md菜单"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    if isinstance(bot, QQ_Bot):
        if plugin_config.splatoon3_qq_md_mode:
            # 发送md
            if isinstance(event, QQ_C2CME):
                user_id = ""
            # 发送md
            await bot_send_more_nso_help_md(bot, event, user_id)
            return
        else:
            # 发送文本
            msg = "未开启md模版选项，二级md菜单功能不可用"
            await bot_send(bot, event, msg)
            return