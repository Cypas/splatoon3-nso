import base64
import json
import os

from .send_msg import bot_send_login_md
from ..config import plugin_config
from ..data.data_source import dict_get_or_set_user_info, model_get_or_set_user, dict_clear_one_user_info_dict
from ..utils import DIR_RESOURCE
from ..utils.bot import *

# 图标文件夹
icons_folder = os.path.join(DIR_RESOURCE, "icons")
PUSH_INTERVAL = 15  # push推送循环时间

# 真格入场券点数
DICT_RANK_POINT = {
    'C-': 0,
    'C': -20,
    'C+': -40,
    'B-': -55,
    'B': -70,
    'B+': -85,
    'A-': -110,
    'A': -120,
    'A+': -130,
    'S': -170,
    'S+': -180,
}

# 徽章排名
dict_badges_ranking = {
    "QmFkZ2UtMzEwMTAwMA==": "j3000",  # 绿X 3000名  仅按日服计算  Badge-3101000
    # "QmFkZ2UtMzEwMTAwMQ==": "j500",  # 银X 500名 Badge-3101001
    # "QmFkZ2UtMzEwMTAwMg==": "j10",  # 金X 10名 Badge-3101002
    "QmFkZ2UtMzEwMTEwMA==": "j2000+",  # 日服 2000+章 Badge-3101100
    "QmFkZ2UtMzEwMTEwMQ==": "e2000+",  # 美服 2000+章 Badge-3101101
    "QmFkZ2UtMzEwMTIwMA==": "j2000+",  # 日服 x2000+时连赢15局 Badge-3101200
    "QmFkZ2UtMzEwMTIwMQ==": "e2000+",  # 美服 x2000+时连赢15局 Badge-3101201
    "QmFkZ2UtMzEwMTIxMA==": "j2000+",  # 日服 x2000+时连赢70局 Badge-3101210
    "QmFkZ2UtMzEwMTIxMQ==": "e2000+",  # 美服 x2000+时连赢70局 Badge-3101211
    "QmFkZ2UtMzEwMTIyMA==": "j2000+",  # 日服 x2000+时连赢350局 Badge-3101220
    "QmFkZ2UtMzEwMTIyMQ==": "e2000+",  # 美服 x2000+时连赢350局 Badge-3101221

    "QmFkZ2UtMzEwMTMwMA==": "j50000",  # 日服 50000 Badge-3101300
    "QmFkZ2UtMzEwMTMwMQ==": "e50000",  # 美服 50000 Badge-3101301
    "QmFkZ2UtMzEwMTMxMA==": "j30000",  # 日服 30000 Badge-3101310
    "QmFkZ2UtMzEwMTMxMQ==": "e30000",  # 美服 30000  Badge-3101311
    "QmFkZ2UtMzEwMTMyMA==": "j10000",  # 日服 10000  Badge-3101320
    "QmFkZ2UtMzEwMTMyMQ==": "e10000",  # 美服 10000 Badge-3101321
    "QmFkZ2UtMzEwMTMzMA==": "j5000",  # 日服 5000 Badge-3101330
    "QmFkZ2UtMzEwMTMzMQ==": "e5000",  # 美服 5000 Badge-3101331
    "QmFkZ2UtMzEwMTM0MA==": "j3000",  # 日服 3000 Badge-3101340
    "QmFkZ2UtMzEwMTM0MQ==": "e3000",  # 美服 3000 Badge-3101341
    "QmFkZ2UtMzEwMTM1MA==": "j1000",  # 日服 1000 Badge-3101350
    "QmFkZ2UtMzEwMTM1MQ==": "e1000",  # 美服 1000 Badge-3101351
    # "QmFkZ2UtMzEwMTM2MA==": "j500",  # 日服 500 Badge-3101360
    # "QmFkZ2UtMzEwMTM2MQ==": "e500",  # 美服 500 Badge-3101361
    # "QmFkZ2UtMzEwMTM3MA==": "j10",  # 日服 10 Badge-3101370
    # "QmFkZ2UtMzEwMTM3MQ==": "e10",  # 美服 10 Badge-3101371
}

# 排名对应分数 2024年6月统计
dict_ranking_point = {
    "j50000": 2144.4,  # 日服排名分数估算
    "j30000": 2255.9,
    "j10000": 2489.6,
    "j5000": 2577.7,
    "j3000": 2641.5,
    "j1000": 2793.9,
    # "j500": 2910.5,
    # "j10": 3449.8,
    "j2000+": 2000,
    "e2000+": 2000,
}

# 对战模式翻译
dict_b_mode_trans = {
    "LEAGUE": "活动比赛",
    "BANKARA": "蛮颓比赛",
    "FEST": "祭典比赛",
    "X_MATCH": "X比赛",
    "REGULAR": "一般比赛",
    "PRIVATE": "私房",

    "CHALLENGE": "挑战",
    "OPEN": "开放",
    "TRI_COLOR": "三色",
}

# icon图标映射
dict_icon_file_map = {
    "活动比赛": "LEAGUE",
    "蛮颓比赛": "BANKARA",
    "祭典比赛": "FEST",
    "X比赛": "X_MATCH",
    "一般比赛": "Regular",
    "私房": "private",

    "蛮颓比赛(挑战)": "BANKARA(CHALLENGE)",
    "蛮颓比赛(开放)": "BANKARA(OPEN)",

    "真格鱼虎对战": "GOAL",
    "真格区域": "AREA",
    "真格塔楼": "LOFT",
    "真格蛤蜊": "CLAM",
    "占地对战": "TURF_WAR",

    "REGULAR": "coop_regular",
    "BIG_RUN": "coop_big_run",
    "TEAM_CONTEST": "coop_team",
}


def get_badges_point(badges_list: list[str]) -> tuple:
    """获取全部徽章内的最高估计x分数"""
    area = ""
    max_ranking = ""
    max_badge = ""
    max_badge_point = 0
    for badge in badges_list:
        if badge in dict_badges_ranking:
            ranking = dict_badges_ranking.get(badge)  # 排名
            if ranking in dict_ranking_point:
                point = dict_ranking_point.get(ranking)  # 分数
                if point > max_badge_point:
                    area = ranking[0]
                    max_ranking = ranking[1:]  # 排名
                    max_badge = badge
                    max_badge_point = point  # 最大值
    return area, max_ranking, max_badge, float(max_badge_point)


def get_icon_path(name, ext_name="png"):
    """获取图标文件路径"""
    if name in dict_icon_file_map:
        # 转化为英文图标名
        name = dict_icon_file_map[name]
        path = os.path.join(icons_folder, "{}.{}".format(name, ext_name))
        if not os.path.exists(path):
            return ""
        return path
    else:
        return name


def get_dict_lang(lang):
    """取不同语言翻译字典"""
    if lang == 'en-US':
        lang = 'en-GB'

    i18n_path = f'{DIR_RESOURCE}/i18n/{lang}.json'
    if not os.path.exists(i18n_path):
        i18n_path = f'{DIR_RESOURCE}/i18n/zh-CN.json'
    with open(i18n_path, 'r', encoding='utf-8') as f:
        dict_lang = json.loads(f.read())
    return dict_lang


def get_game_sp_id_and_name(p):
    """通过对战的成员id获取game_sp_id和name"""
    game_sp_id = (base64.b64decode(p['id']).decode('utf-8') or '').split(':u-')[-1]
    game_name = p['name']
    return game_sp_id, game_name


def get_game_sp_id(battle_id):
    """通过对战id获取game_sp_id"""
    game_sp_id = (base64.b64decode(battle_id).decode('utf-8') or '').split(':u-')[-1]
    return game_sp_id


def get_battle_time_or_coop_time(_id):
    """通过对战的比赛id获取对战或打工开始的时间"""
    start_time = base64.b64decode(_id).decode('utf-8').split('_')[0].split(':')[-1]
    return start_time


def get_battle_true_id(_id):
    """通过对战的比赛id获取里面的真实对战id"""
    """同一场对战在不同列表进行查询，得到的battle_id其实不一样，
    如VsHistoryDetail-u-autukldyq7y5tqlkanmm:RECENT:20240117T044929_a35df573-075d-4d68-ba85-b2db855c98d8
    和VsHistoryDetail-u-autukldyq7y5tqlkanmm:XMATCH:20240117T044929_a35df573-075d-4d68-ba85-b2db855c98d8
    """
    battle_true_id = base64.b64decode(_id).decode('utf-8').split(':')[-1]
    return battle_true_id


async def _check_session_handler(bot: Bot, event: Event, matcher: Matcher):
    """ nonebot 子依赖注入    Check if user has logged in."""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user_info = dict_get_or_set_user_info(platform, user_id)
    if not user_info or not user_info.session_token:
        msg = ""
        if isinstance(bot, Tg_Bot):
            msg = "nso not logged in. direct message to me /login first."
        elif isinstance(bot, QQ_Bot):
            if isinstance(event, QQ_GME) and plugin_config.splatoon3_qq_md_mode:
                # 发送md
                await bot_send_login_md(bot, event, user_id, check_session=True)
                await matcher.finish()
            else:
                msg = "nso未登录，无法使用相关查询\n" \
                      "QQ平台当前无法完成nso登录流程，请至其他平台完成登录后使用/getlc命令获取绑定码\n" \
                      f"Kook服务器id：{plugin_config.splatoon3_kk_guild_id}"
        elif isinstance(bot, All_BOT):
            msg = "nso未登录，无法使用相关查询，请先私信我 /login 进行登录"
        await matcher.finish(msg)
    else:
        # 已登录用户
        # 检查是否同意用户协议
        if not user_info.user_agreement:
            msg = "风险告知:小鱿鱿所使用的nso查询本质上为第三方nso软件，此类第三方调用可能会导致nso鱿鱼圈被封禁，目前未观察到游戏连带被禁的情况。(要怪请去怪乌贼研究所)\n" \
                  "若您希望继续使用小鱿鱿的nso查询功能，请艾特并发送下列指令重新启用nso查询"
            await bot.send(event, msg)
            msg = "/我已知晓nso查询可能导致鱿鱼圈被封禁的风险并重新启用nso查询"
            # await dict_clear_one_user_info_dict(platform, user_id)
            await matcher.finish(msg)
        # cmd_cnt+1
        dict_get_or_set_user_info(platform, user_id, cmd_cnt=user_info.cmd_cnt + 1)


async def get_event_info(bot, event):
    """解析event结构获取group，name等信息"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    data = {'platform': platform,
            'user_id': user_id,
            }
    _event = event.dict() or {}
    if isinstance(bot, Tg_Bot):
        name = _event.get('from_', {}).get('first_name', '')
        if _event.get('from_', {}).get('last_name'):
            name += ' ' + _event.get('from_', {}).get('last_name')
        if not name:
            name = _event.get('from_', {}).get('username') or ''
        data.update({
            'user_name': name,
        })
        # if 'group' in _event.get('chat', {}).get('type', ''):
        #     data.update({
        #         'group_id': _event['chat']['id'],
        #         'group_name': _event.get('chat', {}).get('title', ''),
        #     })
    elif isinstance(bot, Kook_Bot):
        data.update({
            'user_name': _event.get('event', {}).get('author', {}).get('username') or '',
        })
        # if 'group' in event.get_event_name():
        #     server_id = _event.get('event', {}).get('guild_id')
        #     server_name = ''
        #     channel_id = _event.get('target_id') or ''
        #     channel_name = _event.get('event', {}).get('channel_name', '')
        #     try:
        #         res = await bot.guild_view(guild_id=server_id)
        #         server_name = res.name
        #         if server_name:
        #             server_name += '-'
        #     except Exception as ex:
        #         logger.warning(f'get guild ({server_id}) ex: {ex}')
        #     data.update({
        #         'group_id': server_id or channel_id,
        #         'group_name': f'{server_name}{channel_name}',
        #     })
    elif isinstance(bot, QQ_Bot):
        if isinstance(event, (QQ_CME, QQ_PME)):
            # qq 频道, qq 频道私聊
            data.update({
                'user_name': _event.get('author', {}).get('username'),
            })

        elif isinstance(event, QQ_GME):
            # qq 群
            data.update({
                'user_name': 'QQ群',
            })
        elif isinstance(event, QQ_C2CME):
            # c2c私信
            data.update({
                'user_name': 'C2C',
            })
        # if 'group' in event.get_event_name():
        # qq 都在群里使用
        # data.update({
        #     'group_id': _event.get('guild_id') or _event.get('group_openid') or '',
        #     'group_name': _event.get('guild_id') or _event.get('group_openid') or '',
        # })
    elif isinstance(bot, V11_Bot):
        data.update({
            'user_name': _event.get('sender', {}).get('nickname', ''),
        })
    elif isinstance(bot, V12_Bot):
        user_name = ''
        user = model_get_or_set_user(platform, user_id)
        if user:
            user_name = user.user_name
        if not user_name:
            user_info = await bot.get_user_info(user_id=user_id)
            if user_info:
                user_name = user_info.get('user_name', '')

        data.update({
            'user_name': user_name,
        })

    return data

# event结构解析参考代码
# async def log_cmd_to_db(bot, event, get_map=False):
#     try:
#         message = event.get_plaintext().strip()
#         _event = event.dict() or {}
#         user_id = event.get_user_id()
#
#         data = {'user_id': user_id, 'cmd': message}
#         if isinstance(bot, QQBot):
#             data.update({
#                 'id_type': 'qq',
#                 'username': _event.get('sender', {}).get('nickname', '')
#             })
#             group_id = _event.get('group_id')
#             if group_id:
#                 group_name = ''
#                 group_lst = get_all_group()
#                 for g in group_lst:
#                     if str(g.group_id) == str(group_id):
#                         group_name = g.group_name
#                         break
#
#                 if not group_name:
#                     group_info = await bot.call_api('get_group_info', group_id=group_id)
#                     group_name = group_info.get('group_name')
#                     if group_name:
#                         set_db_info(group_id=group_id, id_type='qq', group_name=group_name)
#
#                 data.update({
#                     'group_id': group_id,
#                     'group_name': group_name,
#                 })
#
#         elif isinstance(bot, TGBot):
#             name = _event.get('from_', {}).get('first_name', '')
#             if _event.get('from_', {}).get('last_name'):
#                 name += ' ' + _event.get('from_', {}).get('last_name')
#             if not name:
#                 name = _event.get('from_', {}).get('username') or ''
#
#             data.update({
#                 'id_type': 'tg',
#                 'username': name,
#                 'first_name': _event.get('from_', {}).get('first_name', ''),
#                 'last_name': _event.get('from_', {}).get('last_name', ''),
#             })
#             if 'group' in _event.get('chat', {}).get('type', ''):
#                 data.update({
#                     'group_id': _event['chat']['id'],
#                     'group_name': _event.get('chat', {}).get('title', ''),
#                 })
#
#         elif isinstance(bot, WXBot):
#             username = ''
#             user = get_user(user_id=user_id)
#             if user:
#                 username = user.username
#             if not username:
#                 user_info = await bot.get_user_info(user_id=user_id)
#                 if user_info:
#                     username = user_info.get('user_name', '')
#             data.update({
#                 'id_type': 'wx',
#                 'username': username
#             })
#             group_id = _event.get('group_id')
#             if group_id:
#                 group_name = ''
#                 group_lst = get_all_group()
#                 for g in group_lst:
#                     if str(g.group_id) == str(group_id):
#                         group_name = g.group_name
#                         break
#
#                 if not group_name:
#                     group_info = await bot.get_group_info(group_id=group_id)
#                     group_name = group_info.get('group_name')
#                     if group_name:
#                         set_db_info(group_id=group_id, id_type='qq', group_name=group_name)
#
#                 data.update({
#                     'group_id': group_id,
#                     'group_name': group_name,
#                 })
