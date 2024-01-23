from collections import defaultdict
from datetime import datetime as dt, timedelta

import unicodedata

from .send_msg import bot_send
from .utils import _check_session_handler, get_game_sp_id_and_name
from ..data.data_source import dict_get_or_set_user_info, model_get_temp_image_path
from ..s3s.splatoon import Splatoon
from ..utils.bot import *


@on_command("me", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def me(bot: Bot, event: Event):
    """查询 我的"""
    await bot_send(bot, event, message="请求个人数据中，请稍等...")

    from_group = False
    if 'group' in event.get_event_name() or isinstance(bot, QQ_Bot):
        from_group = True

    msg = await get_me(bot, event, from_group)
    await bot_send(bot, event, msg, image_width=450)


async def get_me(bot, event, from_group):
    """获取我的各种信息"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    history_summary = await splatoon.get_history_summary()
    total_query = await splatoon.get_total_query(try_again=True)
    coop = await splatoon.get_coops(try_again=True)

    try:
        msg = await get_me_md(user, history_summary, total_query, coop, from_group)
    except Exception as e:
        logger.exception(e)
        msg = f'获取数据失败，请稍后再试'
    return msg


async def get_me_md(user, summary, total, coops, from_group=False):
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
        coop_msg = f"""当前打工段位 | {level}
现有点数 | {card['regularPoint']}
打工次数 | {card['playCount']}
金鲑鱼卵 | {card['goldenDeliverCount']} {gdpc}
鲑鱼卵 | {card['deliverCount']} {dpc}
头目鲑鱼 | {card['defeatBossCount']} {boss_per_cnt}
救援次数 | {card['rescueCount']} {rpc}
累计点数 | {card['totalPoint']} {ppc}
鳞片 | 🥉{p['bronze']} 🥈{p['silver']} 🏅️{p['gold']}"""

        if from_group:
            coop_msg = f"""当前打工段位 | {level}
打工次数 | {card['playCount']}
头目鲑鱼 | {card['defeatBossCount']} {boss_per_cnt}
鳞片 | 🥉{p['bronze']} 🥈{p['silver']} 🏅️{p['gold']}"""

    ar = (history.get('xMatchMaxAr') or {}).get('power') or 0  # 区域
    lf = (history.get('xMatchMaxLf') or {}).get('power') or 0  # 塔楼
    gl = (history.get('xMatchMaxGl') or {}).get('power') or 0  # 鱼虎
    cl = (history.get('xMatchMaxCl') or {}).get('power') or 0  # 蛤蜊
    x_msg = '||'
    if any([ar, lf, gl, cl]) and not from_group:
        x_msg = f"X赛最高战力 | 区域:{ar:>7.2f}, 塔楼:{lf:>7.2f}<br> 鱼虎:{gl:>7.2f}, 蛤蜊:{cl:>7.2f}\n||"

    _league = ''
    _open = ''
    if history.get('leagueMatchPlayHistory'):
        _l = history['leagueMatchPlayHistory']
        _n = _l['attend'] - _l['gold'] - _l['silver'] - _l['bronze']
        _league = f"🏅️{_l['gold']:>3} 🥈{_l['silver']:>3} 🥉{_l['bronze']:>3} &nbsp; {_n:>3} ({_l['attend']})"
    if history.get('bankaraMatchOpenPlayHistory'):
        _o = history['bankaraMatchOpenPlayHistory']
        _n = _o['attend'] - _o['gold'] - _o['silver'] - _o['bronze']
        _open = f"🏅️{_o['gold']:>3} 🥈{_o['silver']:>3} 🥉{_o['bronze']:>3} &nbsp; {_n:>3} ({_o['attend']})"

    player_name = player['name'].replace('`', '&#96;').replace('|', '&#124;')
    name_id = player['nameId']
    user_name = f'{player_name} #{name_id}'

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
                b_img = await model_get_temp_image_path('badges', _b_id, _b_url)
                _style = f'position:absolute;margin-top:-4px;margin-left:{_idx * 30}px'
                badges_str += f'''<img height='30px' style='{_style}' src="{b_img}"/>'''
        _idx += 1

    msg = f"""####
|||
|--------------:|---|
{w_img} |{user_name}
{img} |{player['byname']}
等级 | {history['rank']} {badges_str}
技术 | {history['udemae']}
最高技术 | {history['udemaeMax']}
总胜利数 | {history['winCountTotal']}{all_cnt} {r}
涂墨面积 | {history['paintPointTotal']:,}p
徽章 | {len(history['badges'])}
活动 | {_league}
开放 | {_open}
首次游玩 | {s_time:%Y-%m-%d %H:%M:%S} +08:00
当前时间 | {c_time:%Y-%m-%d %H:%M:%S} +08:00
{x_msg}
{coop_msg}
|||
"""
    return msg


@on_command("friends", aliases={'fr'}, priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def friends(bot: Bot, event: Event):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg = await get_friends_md(splatoon)
    await bot_send(bot, event, msg, image_width=600)


async def get_friends_md(splatoon, lang='zh-CN'):
    res = await splatoon.get_friends()
    if not res:
        return '网络错误，请稍后再试.'

    msg = f'''#### 在线好友 HKT {dt.now():%Y-%m-%d %H:%M:%S}
||||||
|---:|---|:---|:---|---|
'''
    _dict = defaultdict(int)
    for f in res['data']['friends']['nodes']:
        if f.get('onlineState') == 'OFFLINE':
            continue
        _state = fmt_sp3_state(f)
        _state = get_cn_sp3_stat(_state)

        _dict[_state] += 1
        n = f['playerName'] or f.get('nickname')
        n = n.replace('`', '&#96;').replace('|', '&#124;')

        img_type = "friend_icon"
        # 储存名使用friend_id
        icon_img = await model_get_temp_image_path(img_type, f['id'], f['userIcon']['url'])
        img = f'''<img height="40" src="{icon_img}"/>'''
        if f['playerName'] and f['playerName'] != f['nickname']:
            nickname = f['nickname'].replace('`', '&#96;').replace('|', '&#124;')
            n = f'{f["playerName"]}|{img}|{nickname}'
        else:
            n = f'{n}|{img}|'
        msg += f'''|{n}| {_state}|\n'''

    msg += '||\n'
    _dict['TOTAL'] = sum(_dict.values())
    for k, v in _dict.items():
        msg += f'||||{k}| {v}|\n'
    msg += '||\n'
    return msg


@on_command("ns_friends", aliases={'ns_fr'}, priority=10, block=True).handle(
    parameterless=[Depends(_check_session_handler)])
async def ns_friends(bot: Bot, event: Event):
    """获取ns好友"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg = await get_ns_friends_md(splatoon)
    await bot_send(bot, event, msg, image_width=680)


async def get_ns_friends_md(splatoon: Splatoon):
    """获取ns好友md"""
    res = await splatoon.app_ns_friend_list() or {}
    res = res.get('result')
    if not res:
        logger.info(f"get_ns_friends result error,res: {res}")
        return 'No friends found!'

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
                dict_sp3[f.get('nickname')] = _state
                _dict_sp3[_state] += 1

    msg = ''
    _dict = defaultdict(int)
    for f in res.get('friends') or []:
        if (f.get('presence') or {}).get('state') != 'ONLINE' and f.get('isFavoriteFriend') is False:
            continue
        u_name = f.get('name') or ''
        ww = 10 - wide_chars(u_name)
        msg += f"{u_name:<{ww}}\t"
        if (f.get('presence') or {}).get('state') == 'ONLINE':
            _game_name = f['presence']['game'].get('name') or ''
            _game_name = _game_name.replace('The Legend of Zelda: Tears of the Kingdom', 'TOTK')
            msg += f" {_game_name}"
            _dict[_game_name] += 1
            if f['presence']['game'].get('totalPlayTime'):
                msg += f"({int(f['presence']['game'].get('totalPlayTime') / 60)}h)"
            if f.get('name') in dict_sp3:
                msg += f" | {dict_sp3[f.get('name')]}"
        else:
            t = (f.get('presence') or {}).get('logoutAt') or 0
            if t:
                delt = str(dt.utcnow() - dt.utcfromtimestamp(t))
                tt = delt
                if tt.startswith('0'):
                    tt = tt.split(', ')[-1]
                tt = tt.split('.')[0][:-3].replace(':', 'h')
                msg += f" (offline about {tt})"
            else:
                msg += f" ({(f.get('presence') or {}).get('state', 'offline')})"
        msg += '\n'
    st = ''
    _dict['total online'] = sum(_dict.values())
    _dict['total'] = len(res.get('friends') or [])
    for k, v in _dict.items():
        st += f'{k:>25}: {v}\n'

    if _dict_sp3:
        _dict_sp3['total sp3'] = sum(_dict_sp3.values())
        st += '\n'
        for k, v in _dict_sp3.items():
            st += f'{k:>25}: {v}\n'

    msg = f'''```
{msg}
{st}
```'''
    return msg


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
    if 'PRIVATE' in _st:
        _st = '私房'
    elif 'X_MATCH)' in _st:
        _st = 'X比赛'
    elif 'RA)O' in _st:
        _st = '开放'
    elif 'RA)C' in _st:
        _st = '挑战'
    elif 'MATCHING' in _st:
        _st = '匹配中'
    elif 'COOP' in _st:
        _st = '打工'
    elif 'REGULAR)' in _st:
        _st = '涂地'
    elif _st == 'ONLINE':
        _st = '在线'
    elif 'LEAGUE' in _st:
        _st = '活动'
    elif 'FEST)O' in _st:
        _st = '祭典开放'
    elif 'FEST)C' in _st:
        _st = '祭典挑战'
    elif 'FEST)3' in _st:
        _st = '祭典三色'
    return _st