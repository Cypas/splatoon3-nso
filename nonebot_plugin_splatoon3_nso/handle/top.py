from datetime import datetime as dt, timedelta

from .last import get_last_battle_or_coop
from .send_msg import bot_send
from .utils import _check_session_handler, get_battle_time_or_coop_time
from ..data.data_source import model_get_temp_image_path, dict_get_or_set_user_info, model_get_max_power_top_all, \
    model_get_all_user, model_get_all_weapon, model_get_one_user, model_get_all_top_all
from ..s3s.splatoon import Splatoon
from ..utils import get_msg_id, get_time_now_china_date, time_converter, get_time_now_china_str, utc_str_to_china_str
from ..utils.bot import *

matcher_top = on_command("top", priority=10, block=True)

@matcher_top.handle(parameterless=[Depends(_check_session_handler)])
async def _top(bot: Bot, event: Event, args: Message = CommandArg()):
    """top查询"""
    cmd_message = args.extract_plain_text().strip()
    logger.debug(f'top: {cmd_message}')
    battle = None
    player_idx = None
    get_all = False
    if cmd_message:
        cmd_lst = cmd_message.split()
        for cmd in cmd_lst:
            cmd = cmd.strip()
            if not cmd:
                continue
            if cmd.isdigit():
                battle = int(cmd)
            else:
                player_idx = cmd.lower()
            if cmd == 'last':
                get_all = True

    if battle:
        battle = max(1, battle)
        battle = min(50, battle)
    if player_idx:
        if len(player_idx) != 1 or player_idx not in 'abcdefgh':
            player_idx = 1
        else:
            player_idx = ord(player_idx) - ord('a') + 1

    if battle and not player_idx:
        player_idx = 1
    if player_idx and not battle:
        battle = 1

    if get_all:
        # -1代表获取全部成员
        player_idx = '-1'

    _msg = '未查询到任何上榜数据\n/top未添加任何参数时，默认会查询自己在x赛500强，任意活动前100，任意祭典百杰 中查询数据，若以上榜单都未上榜，则查不到数据，/top命令具体参数可查看/nso详细帮助'
    photo = await get_top(bot, event, battle=battle, player_idx=player_idx)
    if photo:
        if not photo.startswith('###'):
            _msg += f', {photo}'
        else:
            _msg = photo
    await bot_send(bot, event, _msg)


async def get_top(bot: Bot, event: Event, battle=None, player_idx=None):
    player_name = ''
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    logger.info(f'get_top: {msg_id}, {battle}, {player_idx}')

    user = dict_get_or_set_user_info(platform, user_id)
    player_code = user.game_sp_id
    if battle:
        res = await get_last_battle_or_coop(bot, event, get_battle=True, idx=battle - 1, get_player_code_idx=player_idx)
        if isinstance(res, tuple):
            # 筛选单一玩家
            player_code, player_name = res
        else:
            # last 全部玩家
            p_lst = []
            _i = 64
            for p in res:
                _i += 1
                if p[0] != player_code:
                    p_lst.append(f"{p[0]}_{chr(_i)}")
            player_code = p_lst

    photo = await get_top_md(player_code)
    return photo or player_name


async def get_top_md(player_code: str | list):
    logger.info(f'get top md {player_code}')
    msg = ''
    dict_p = {}
    if isinstance(player_code, str):
        res = model_get_max_power_top_all(player_code)
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

    weapon = model_get_all_weapon() or {}

    str_player_code = ''
    if isinstance(player_code, str):
        str_player_code = f'({player_code})'

    msg = f'''#### 排行榜数据 {str_player_code} HKT {dt.now():%Y-%m-%d %H:%M:%S}
|||||||
|---|---:|:---|---|---|---|
'''

    if isinstance(player_code, list):
        msg = f'''#### 排行榜数据 {str_player_code} HKT {dt.now():%Y-%m-%d %H:%M:%S}
||||||||
|---|---:|:---|---|---|---|---|
'''

    p_code = ''
    if res:
        p_code = res[0].player_code
    for i in res:
        t_type = i.top_type
        if 'LeagueMatchRankingTeam' in t_type:
            t_lst = t_type.split(':')
            t_type = f'{t_lst[0]}:{t_lst[3]}'
            i.play_time += timedelta(hours=8)
        t_type = t_type.replace('LeagueMatchRankingTeam-', 'L-')
        _t = f"{i.play_time:%y-%m-%d %H}".replace(' 00', '')
        if weapon.get(str(i.weapon_id)):
            img_type = "battle_weapon_main"
            weapon_main_img = await model_get_temp_image_path(img_type, weapon[str(i.weapon_id)]['name'],
                                                              weapon[str(i.weapon_id)]['url'])
            str_w = f'<img height="40" src="{weapon_main_img}"/>'
        else:
            str_w = f'{i.weapon}'
        if i.player_code != p_code:
            msg += f'||\n'
            p_code = i.player_code
        if isinstance(player_code, str):
            msg += f'{t_type}|{i.rank}|{i.power}|{str_w}|{i.player_name}|{_t}\n'
        else:
            msg += f'{t_type}|{i.rank}|{i.power}|{str_w}|{i.player_name}|{dict_p[i.player_code]}|{_t}\n'

    msg += '||\n\n说明: /top [1-50] [a-h] [last]. 对战数字, 玩家排序, 全部查询\n'
    return msg


@on_command("x_top", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def x_top(bot: Bot, event: Event):
    """x_top查询"""
    msg = await get_x_top_msg(bot, event)
    await bot_send(bot, event, msg)


async def get_x_top_msg(bot, event):
    if bot and event:
        # 提供了bot和event 来自用户请求
        platform = bot.adapter.get_name()
        user_id = event.get_user_id()
        user = dict_get_or_set_user_info(platform, user_id)
        splatoon = Splatoon(bot, event, user)
    else:
        # 没有bot和event 来自定时任务
        # 随机抽一名登录用户
        db_user = model_get_one_user()
        user = dict_get_or_set_user_info(db_user.platform, db_user.user_id)
        splatoon = Splatoon(None, None, user)

    msg = await get_x_top_md(splatoon)
    return msg


async def get_x_top_md(splatoon):
    """获取x排行榜md"""
    try:
        jp_res = await splatoon.get_x_ranking('PACIFIC')  # 日服 暇古
        us_res = await splatoon.get_x_ranking('ATLANTIC', try_again=True)  # 美服 艾洛眼
    except ValueError:
        return '网络错误，请稍后再试...'
    except Exception as e:
        return 'No X found!'

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
