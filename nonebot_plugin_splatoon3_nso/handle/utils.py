import base64
import json
import os

from .send_msg import bot_send_login_md
from ..config import plugin_config
from ..data.data_source import dict_get_or_set_user_info
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


async def _check_session_handler(bot: Bot, event: Event, matcher: Matcher):
    """ nonebot 子依赖注入    Check if user has logged in."""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user_info = dict_get_or_set_user_info(platform, user_id)
    if not user_info or not user_info.session_token:
        msg = ""
        if isinstance(bot, Tg_Bot):
            msg = "nso not logged in. direct message to me /login first."
        elif isinstance(bot, (V11_Bot, V12_Bot, Kook_Bot)):
            msg = "nso未登录，无法使用相关查询，请先私信我 /login 进行登录"
        elif isinstance(bot, QQ_Bot):
            if isinstance(event, QQ_GME) and plugin_config.splatoon3_qq_md_mode:
                # 发送md
                await bot_send_login_md(bot, event, user_id, check_session=True)
                await matcher.finish()
            else:
                msg = "nso未登录，无法使用相关查询\n" \
                       "QQ平台当前无法完成nso登录流程，请至其他平台完成登录后获取绑定码\n" \
                       f"Kook服务器id：{plugin_config.splatoon3_kk_guild_id}"

        await matcher.finish(msg)
    else:
        # 已登录用户
        # cmd_cnt+1
        dict_get_or_set_user_info(platform, user_id, cmd_cnt=user_info.cmd_cnt + 1)


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
