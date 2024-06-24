from collections import defaultdict
from datetime import datetime as dt, timedelta

import unicodedata
from nonebot import on_keyword

from .send_msg import bot_send
from .utils import _check_session_handler
from ..data.data_source import dict_get_or_set_user_info, model_get_temp_image_path, model_get_or_set_user, \
    model_get_power_rank, model_set_user_friend, model_get_another_account_user, global_user_info_dict, model_get_all_top_all
from ..data.utils import GlobalUserInfo
from ..s3s.splatoon import Splatoon
from ..utils import get_msg_id
from ..utils.bot import *


@on_command("me", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def me(bot: Bot, event: Event):
    """查询 我的"""
    await bot_send(bot, event, message="请求个人数据中，请稍等...")

    from_group = False
    if isinstance(event, All_Group_Message):
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
    if not history_summary:
        history_summary = await splatoon.get_history_summary(multiple=True)
    total_query = await splatoon.get_total_query(multiple=True)
    if not total_query:
        total_query = await splatoon.get_total_query(multiple=True)
    coop = await splatoon.get_coops(multiple=True)
    if not coop:
        coop = await splatoon.get_coops(multiple=True)

    try:
        msg = await get_me_md(user, history_summary, total_query, coop, from_group)
    except Exception as e:
        logger.exception(e)
        msg = f"获取数据失败，请稍后再试"
    finally:
        # 关闭连接池
        await splatoon.req_client.close()
    return msg


async def get_me_md(user: GlobalUserInfo, summary, total, coops, from_group=False):
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
鳞片 | 🏅️{p['gold']} 🥈{p['silver']} 🥉{p['bronze']}"""

        if from_group:
            coop_msg = f"""当前打工段位 | {level}
打工次数 | {card['playCount']}
头目鲑鱼 | {card['defeatBossCount']} {boss_per_cnt}
鳞片 | 🏅️{p['gold']} 🥈{p['silver']} 🥉{p['bronze']}"""

    ar = (history.get('xMatchMaxAr') or {}).get('power') or 0  # 区域
    lf = (history.get('xMatchMaxLf') or {}).get('power') or 0  # 塔楼
    gl = (history.get('xMatchMaxGl') or {}).get('power') or 0  # 鱼虎
    cl = (history.get('xMatchMaxCl') or {}).get('power') or 0  # 蛤蜊
    x_msg = '||'
    if any([ar, lf, gl, cl]) and not from_group:
        x_msg = f"X赛最高战力 | 区域:{ar:>7.2f}, 塔楼:{lf:>7.2f}<br> 鱼虎:{gl:>7.2f}, 蛤蜊:{cl:>7.2f}\n||"
    if any([ar, lf, gl, cl]):
        _dict_rank = model_get_power_rank()
        _rank = _dict_rank.get(user.game_sp_id)
        if _rank:
            x_msg = x_msg.replace('||', f'X赛最高战力</br>bot排名 | {_rank}\n||')

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
                b_img = await model_get_temp_image_path('user_nameplate_badge', _b_id, _b_url)
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
    top_res = model_get_all_top_all(user.game_sp_id)
    if top_res:
        msg += f"上榜记录 | {len(top_res)}次 &nbsp;&nbsp; /top 查询排行榜\n"
    return msg


@on_command("friends", aliases={'friend', 'fr'}, priority=10, block=True).handle(
    parameterless=[Depends(_check_session_handler)])
async def friends(bot: Bot, event: Event):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg = await get_friends_md(splatoon)
    # 关闭连接池
    await splatoon.req_client.close()
    await bot_send(bot, event, msg, image_width=600)


async def get_friends_md(splatoon, lang='zh-CN'):
    res = await splatoon.get_friends()
    if not res:
        return 'bot网络错误，请稍后再试.'

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


@on_command("ns_friends", aliases={'ns_friend', 'ns_fr', 'nsfr'}, priority=10, block=True).handle(
    parameterless=[Depends(_check_session_handler)])
async def ns_friends(bot: Bot, event: Event):
    """获取ns好友"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg = await get_ns_friends_md(splatoon)
    # 关闭连接池
    await splatoon.req_client.close()
    await bot_send(bot, event, msg, image_width=680)


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
                _state = get_cn_sp3_stat(_state)
                dict_sp3[f.get('nickname')] = _state
                _dict_sp3[_state] += 1

    msg = f'''#### NS在线好友 HKT {dt.now():%Y-%m-%d %H:%M:%S}
|||||
|---:|---|---|:---|
'''
    _dict = defaultdict(int)
    for f in res.get('friends') or []:
        if (f.get('presence') or {}).get('state') != 'ONLINE' and f.get('isFavoriteFriend') is False:
            continue
        u_name = f.get('name') or ''
        u_name = u_name.replace('`', '&#96;').replace('|', '&#124;')

        img_type = "ns_friend_icon"
        # 储存名使用friend_id
        icon_img = await model_get_temp_image_path(img_type, f['nsaId'], f['imageUri'])
        img_str = f'''<img height="40" src="{icon_img}"/>'''
        msg += f'|{u_name}|{img_str}'
        if (f.get('presence') or {}).get('state') == 'ONLINE':
            _game_name = f['presence']['game'].get('name') or ''
            _game_name = _game_name.replace('The Legend of Zelda: Tears of the Kingdom', 'TOTK')
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
        msg += f"\n\n如果ns主机主动更换了ns码导致无法搜索到好友，请发送\n/friend_code force 指令重新缓存新的好友码"
    else:
        splatoon = Splatoon(bot, event, user)
        res = {}
        try:
            res = await splatoon.app_ns_myself() or {}
        except Exception as e:
            logger.error(f"{msg_id} get friend_code error:{e}")
            msg = "bot网络错误，请稍后再试"
        finally:
            # 关闭连接池
            await splatoon.req_client.close()

        name = res.get('name')
        code = res.get('code')
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
async def my_icon(bot: Bot, event: Event):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = model_get_or_set_user(platform, user_id)
    msg = ""
    msg_error = "本地未缓存nso头像，请在使用一次/me 命令进行缓存后重试"
    if user.game_sp_id:
        my_icon_path = await model_get_temp_image_path('my_icon', user.game_sp_id)
        if my_icon_path:
            with open(my_icon_path, "rb") as f:
                _my_icon = f.read()
                msg = _my_icon
        else:
            msg = msg_error
    else:
        msg = msg_error

    await bot_send(bot, event, message=msg)


@on_keyword({"我已知晓nso查询可能导致鱿鱼圈被封禁的风险并重新启用nso查询"}, block=True).handle()
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

