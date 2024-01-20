import base64
import json
import os

from ..config import plugin_config
from ..data.data_source import global_user_info_dict, model_get_temp_image_path, dict_get_or_set_user_info, \
    model_get_user_friend, model_get_login_user
from ..utils import DIR_RESOURCE
from ..utils.bot import *

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

# 对战模式翻译
dict_b_mode_trans = {
    "LEAGUE": "活动比赛",
    "BANKARA": "蛮颓比赛",
    "FEST": "祭典比赛",
    "X_MATCH": "X比赛",
    "REGULAR": "一般比赛",

    "CHALLENGE": "挑战",
    "OPEN": "开放",
    "TRI_COLOR": "三色",
}


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


async def get_user_name_color(player_name, player_code):
    """取用户名颜色"""
    login = model_get_login_user(player_code)

    # 登录用户绿色
    if login:
        return f'<span style="color:green">{player_name}</span>'

    u_str = player_name
    r = model_get_user_friend(player_name)
    # 用户好友蓝色
    if r:
        img_type = "friend_icon"
        # 储存名使用friend_id
        user_icon = await model_get_temp_image_path(img_type, r.friend_id, r.user_icon)
        img = f"<img height='36px' style='position:absolute;right:5px;margin-top:-6px' src='{user_icon}'/>"
        u_str = f'<span style="color:skyblue">{player_name} {img}</span>'
    return u_str


async def _check_session_handler(bot: Bot, event: Event, matcher: Matcher):
    """ nonebot 子依赖注入    Check if user has logged in."""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user_info = dict_get_or_set_user_info(platform, user_id)
    if not user_info or not user_info.session_token:
        _msg = ""
        if isinstance(bot, Tg_Bot):
            _msg = "Permission denied. /login first."
        elif isinstance(bot, (V11_Bot, V12_Bot, Kook_Bot, QQ_Bot)):
            _msg = '无权限查看，请先 /login 登录'
        await matcher.finish(_msg)


async def get_event_info(bot, event):
    """解析event结构获取group，name等信息"""
    data = {'platform': bot.adapter.get_name(),
            'user_id': event.get_user_id(),
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
        if _event.get('guild_id'):
            # qq 频道
            data.update({
                'user_name': _event.get('author', {}).get('username'),
            })

        else:
            # qq 群
            data.update({
                'user_name': 'QQ群',
            })
        # if 'group' in event.get_event_name():
        # qq 都在群里使用
        # data.update({
        #     'group_id': _event.get('guild_id') or _event.get('group_openid') or '',
        #     'group_name': _event.get('guild_id') or _event.get('group_openid') or '',
        # })
    return data
