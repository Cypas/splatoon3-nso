from datetime import datetime as dt, timedelta

from .last import get_last_battle_or_coop
from .send_msg import bot_send
from .utils import _check_session_handler
from ..data.data_source import model_get_temp_image_path, dict_get_or_set_user_info, model_get_all_top_all
from ..s3s.splatoon import Splatoon
from ..utils import get_msg_id, utc_str_to_china_str
from ..utils.bot import *

matcher_top = on_command("top", priority=10, block=True)


@matcher_top.handle(parameterless=[Depends(_check_session_handler)])
async def _top(bot: Bot, event: Event, args: Message = CommandArg()):
    """top查询"""
    cmd_message = args.extract_plain_text().strip()
    logger.debug(f'top: {cmd_message}')
    battle_idx = None
    player_idx = None
    get_all = False
    if cmd_message:
        cmd_lst = cmd_message.split()
        for cmd in cmd_lst:
            cmd = cmd.strip()
            if not cmd:
                continue
            if cmd.isdigit():
                battle_idx = int(cmd)
            else:
                player_idx = cmd.lower()
            if cmd == 'last' or cmd == 'all':
                get_all = True

    if battle_idx:
        battle_idx = max(1, battle_idx)
        battle_idx = min(50, battle_idx)
    if player_idx:
        if len(player_idx) != 1 or player_idx not in 'abcdefgh':
            player_idx = 1
        else:
            player_idx = ord(player_idx) - ord('a') + 1

    if battle_idx and not player_idx:
        player_idx = 1
    if player_idx and not battle_idx:
        battle_idx = 1

    if get_all:
        # -1代表获取全部成员
        player_idx = "-1"

    _msg = ""
    if not cmd_message:
        _msg += "未查询到自己的任何上榜数据"
        _msg += "\n/top未添加任何参数时，默认会查询自己在x赛500强，任意活动前100，任意祭典百杰 中上榜过的数据\n若以上榜单都未上榜，则查不到数据\n/top命令具体参数可查看/nso帮助"
    else:
        _msg = ''

    top_md = await get_top(bot, event, battle_idx=battle_idx, player_idx=player_idx)
    if top_md:
        if not top_md.startswith('####'):
            # 未查询到数据，top_md值为player_name
            _msg += f"未查询到玩家 {top_md} 上榜数据"
        else:
            _msg = top_md
    elif player_idx == "-1":
        # 全部玩家，且没有上榜数据
        _msg += f"该局对战未查询到任何玩家上榜数据"

    await bot_send(bot, event, _msg)


async def get_top(bot: Bot, event: Event, battle_idx=None, player_idx=None):
    player_name = ''
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    logger.info(f'get_top: {msg_id}, {battle_idx}, {player_idx}')

    user = dict_get_or_set_user_info(platform, user_id)
    player_code = user.game_sp_id
    if battle_idx:
        res = await get_last_battle_or_coop(bot, event, get_battle=True, idx=battle_idx - 1, get_player_code_idx=player_idx)
        if isinstance(res, tuple):
            # 筛选单一玩家
            player_code, player_name = res
        else:
            # all 全部玩家
            p_lst = []
            _i = 96  # 97号为a，为top提供索引
            for p in res:
                _i += 1
                if p[0] != player_code:
                    p_lst.append(f"{p[0]}_{chr(_i)}")
            player_code = p_lst

    top_md = await get_top_md(player_code, player_name)
    # 单一玩家且无记录时 返回player_name
    return top_md or player_name


async def get_top_md(player_code: str | list, player_name=""):
    logger.debug(f'get top md {player_code}')
    msg = ''
    dict_p = {}
    if isinstance(player_code, str):
        res = model_get_all_top_all(player_code)
        if not res:
            return msg
        res = sorted(res, key=lambda x: x.play_time)
        res = res[-30:]
    else:
        res_a = []
        for p in player_code or []:
            p, _name = p.split('_', 1)
            dict_p[p] = _name
            res = model_get_all_top_all(p)
            if res:
                res = sorted(res, key=lambda x: x.play_time)
                res_a.extend(res)
        res = res_a

    # for i in res:
    #     logger.info(f'{i.top_type}, {i.rank}, {i.power}, {i.weapon}')

    if not res:
        return

    # 6列
    msg = f'''#### 全部排行榜数据 (玩家:{player_name}) HKT {dt.now():%Y-%m-%d %H:%M:%S}
|||||||
|---|---:|:---|---|---|---|
|排行榜名称|排名|最高分|武器|玩家|时间|
'''

    # 7列
    if isinstance(player_code, list):
        msg = f'''#### 全部排行榜数据 HKT {dt.now():%Y-%m-%d %H:%M:%S}
||||||||
|---|---:|:---|---|---|---|---|
|排行榜名称|排名|最高分|武器|玩家名|序列|时间|
'''

    p_code = ''
    if res:
        p_code = res[0].player_code

    max_power = 0
    if isinstance(player_code, str) and len(res) > 1:
        max_power = max([i.power for i in res])

    for i in res:
        t_type = i.top_type
        if 'LeagueMatchRankingTeam' in t_type:
            t_lst = t_type.split(':')
            t_type = f'{t_lst[0]}:{t_lst[3]}'
            i.play_time += timedelta(hours=8)
        # LeagueMatchRankingTeam代表的实际是活动
        t_type = t_type.replace('LeagueMatchRankingTeam-', 'E-')
        _t = f"{i.play_time:%y-%m-%d %H}".replace(' 00', '')

        img_type = "battle_weapon_main"
        weapon_main_img = await model_get_temp_image_path(img_type, i.weapon)

        if weapon_main_img:
            str_w = f'<img height="40" src="{weapon_main_img}"/>'
        else:
            str_w = f'{i.weapon}'

        if i.player_code != p_code:
            msg += f'||\n'
            p_code = i.player_code
        if isinstance(player_code, str):
            if max_power and max_power == i.power:
                msg += (f'<span style="color:red">{t_type}</span>|'
                        f'<span style="color:red">{i.rank}</span>|'
                        f'<span style="color:red">{i.power}</span>|{str_w}|{i.player_name}|{_t}\n')
            else:
                msg += f'{t_type}|{i.rank}|{i.power}|{str_w}|{i.player_name}|{_t}\n'
        else:
            msg += f'{t_type}|{i.rank}|{i.power}|{str_w}|{i.player_name}|{dict_p[i.player_code]}|{_t}\n'

    """
    &nbsp;  一个空格
    &emsp;  一个中文宽度
    """

    msg += '||\n\n说明: /top 未添加任何参数时，默认会查询自己在x赛500强，任意活动前100，任意祭典百杰 中查询数据，若以上榜单都未上榜，则查不到数据' \
           '</br>可选参数:[1-50]: 查询倒数第n场对战，配合下面两个参数使用' \
           '</br>&emsp;&emsp;&emsp;&emsp;&nbsp;' \
           '[a-h]: a-h的八个字母对应从上往下的8名玩家，指定查找该玩家全部上榜记录，如 /top 2 e' \
           '</br>&emsp;&emsp;&emsp;&emsp;&nbsp;' \
           'all: all为查询第n场对战中除自己外的7名玩家的全部上榜记录，如 /top 2 all'
    return msg


@on_command("x_top", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def x_top(bot: Bot, event: Event):
    """x_top查询"""
    msg = await get_x_top_msg(bot, event)
    await bot_send(bot, event, msg)


async def get_x_top_msg(bot, event):
    """获取x赛top1"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg = await get_x_top_md(splatoon)
    # 关闭连接池
    await splatoon.req_client.close()
    return msg


async def get_x_top_md(splatoon):
    """获取x排行榜md"""
    try:
        jp_res = await splatoon.get_x_ranking('PACIFIC')  # 日服 暇古
        us_res = await splatoon.get_x_ranking('ATLANTIC', multiple=True)  # 美服 艾洛眼
    except ValueError:
        return "bot网络错误，请稍后再试"
    except Exception as e:
        return "No X found!"

    jp_x = jp_res['data']['xRanking']['currentSeason']
    jp_time = jp_x['lastUpdateTime']
    jp_date_str = utc_str_to_china_str(jp_time)
    jp_region = await region_x_top(jp_x)

    us_x = us_res['data']['xRanking']['currentSeason']
    us_time = us_x['lastUpdateTime']
    us_date_str = utc_str_to_china_str(us_time)
    us_region = await region_x_top(us_x)

    jp_x_region_name = trans_x_region.get(jp_res['data']['xRanking']['region'], jp_res['data']['xRanking']['region'])
    us_x_region_name = trans_x_region.get(us_res['data']['xRanking']['region'], us_res['data']['xRanking']['region'])

    msg = f'''#### X赛顶级玩家 {jp_x['name']}
##### {jp_x_region_name} {jp_date_str}(UTC+8)
{jp_region}
##### {us_x_region_name} {us_date_str}(UTC+8)
{us_region}

'''
    return msg


async def region_x_top(x):
    """整理x_top榜"""
    ar = x['xRankingAr']['nodes'][0]
    lf = x['xRankingLf']['nodes'][0]
    gl = x['xRankingGl']['nodes'][0]
    cl = x['xRankingCl']['nodes'][0]
    ar_w_name = ar['weapon']['name']
    lf_w_name = lf['weapon']['name']
    gl_w_name = gl['weapon']['name']
    cl_w_name = cl['weapon']['name']

    img_type = "battle_weapon_main"
    ar_weapon_main_img = await model_get_temp_image_path(img_type, ar_w_name, ar['weapon']['image']['url'])
    lf_weapon_main_img = await model_get_temp_image_path(img_type, lf_w_name, lf['weapon']['image']['url'])
    gl_weapon_main_img = await model_get_temp_image_path(img_type, gl_w_name, gl['weapon']['image']['url'])
    cl_weapon_main_img = await model_get_temp_image_path(img_type, cl_w_name, cl['weapon']['image']['url'])
    text = f'''\n||||||
|-|-|-|-|-|
|区域|{ar['xPower']}| {ar['name']}\#{ar['nameId']}| {ar_w_name}|<img height="40" src="{ar_weapon_main_img}" />|
|塔楼|{lf['xPower']}| {lf['name']}\#{lf['nameId']}| {lf_w_name}|<img height="40" src="{lf_weapon_main_img}" />|
|鱼虎|{gl['xPower']}| {gl['name']}\#{gl['nameId']}| {gl_w_name}|<img height="40" src="{gl_weapon_main_img}" />|
|蛤蜊|{cl['xPower']}| {cl['name']}\#{cl['nameId']}| {cl_w_name}|<img height="40" src="{cl_weapon_main_img}" />|
'''
    return text


trans_x_region = {
    "PACIFIC": "暇古(日服)",
    "ATLANTIC": "艾洛眼(美服)"
}
