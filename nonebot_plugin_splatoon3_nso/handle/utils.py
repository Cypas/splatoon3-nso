import base64
import json
import os

from ..config import plugin_config
from ..data.data_source import global_user_info_dict, model_get_temp_image_path, dict_get_or_set_user_info, \
    model_get_user_friend, model_get_login_user
from ..utils import DIR_RESOURCE
from ..utils.bot import *

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
    player_sp_id = (base64.b64decode(p['id']).decode('utf-8') or '').split(':u-')[-1]
    player_name = p['name']
    return player_sp_id, player_name


def get_battle_time_or_coop_time(_id):
    """通过对战的比赛id获取对战或打工开始的时间"""
    start_time = base64.b64decode(_id).decode('utf-8').split('_')[0].split(':')[-1]
    return start_time


async def get_user_name_color(player_name, player_code):
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
