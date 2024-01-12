from nonebot.message import event_preprocessor
from nonebot.plugin import PluginMetadata

from .config import driver, plugin_config
from .handle import *
from .utils import MSG_HELP_QQ, MSG_HELP_CN, MSG_HELP
from .utils.bot import *

# require("nonebot_plugin_apscheduler")
# from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="splatoon3游戏nso查询",
    description="一个基于nonebot2框架的splatoon3游戏nso数据查询插件",
    usage="发送 帮助 或 help 可查看详细指令\n",
    type="application",
    # 发布必填，当前有效类型有：`library`（为其他插件编写提供功能），`application`（向机器人用户提供功能）。
    homepage="https://github.com/Cypas/splatoon3-nso",
    # 发布必填。
    supported_adapters={"~onebot.v11", "~onebot.v12", "~telegram", "~kaiheila", "~qq"},
)


@on_startswith(("/", "、"), priority=99).handle()
async def unknown_command(bot: Bot, event: Event):
    logger.info(f'unknown_command {event.get_event_name()}')
    if 'private' in event.get_event_name():
        _msg = "Sorry, I didn't understand that command. /help"
        if isinstance(bot, (V11_Bot, QQ_Bot, V12_Bot, Kook_Bot)):
            _msg = '无效命令，输入 /help 查看帮助'
        await bot.send(event, message=_msg)


@on_command("help", aliases={'h', '帮助', '说明', '文档'}, priority=10).handle()
async def _help(bot: Bot, event: Event):
    # 帮助菜单日程插件优先模式
    if plugin_config.splatoon3_schedule_plugin_priority_mode:
        return
    else:
        if isinstance(bot, Tg_Bot):
            await bot_send(bot, event, message=MSG_HELP, disable_web_page_preview=True)
        elif isinstance(bot, QQ_Bot):
            msg = MSG_HELP_QQ
            await bot_send(bot, event, message=msg)
        elif isinstance(bot, (V12_Bot, Kook_Bot,)):
            msg = MSG_HELP_CN
            await bot_send(bot, event, message=msg)


# @driver.on_startup
# async def bot_on_start():
#     version = utils.BOT_VERSION
#     logger.info(f' bot start, version: {version} '.center(120, '-'))
#     await notify_to_channel(f'bot start, version: {version}')
#
#
# @driver.on_shutdown
# async def bot_on_shutdown():
#     version = utils.BOT_VERSION
#     logger.info(f' bot shutdown, version: {version} '.center(120, 'x'))
#     bots = get_bots()
#     logger.info(f'bot: {bots}')
#     for k in bots.keys():
#         job_id = f'sp3_cron_job_{k}'
#         if scheduler.get_job(job_id):
#             scheduler.remove_job(job_id)
#             logger.info(f'remove job {job_id}!')
#
#
# @driver.on_bot_connect
# async def _(bot: Bot):
#     bot_type = 'Telegram'
#     if isinstance(bot, QQ_Bot):
#         bot_type = 'QQ'
#     elif isinstance(bot, V12_Bot):
#         bot_type = 'WeChat'
#     elif isinstance(bot, Kook_Bot):
#         bot_type = 'Kook'
#
#     logger.info(f' {bot_type} bot connect {bot.self_id} '.center(60, '-').center(120, ' '))
#
#     job_id = f'sp3_cron_job_{bot.self_id}'
#     if scheduler.get_job(job_id):
#         scheduler.remove_job(job_id)
#         logger.info(f'remove job {job_id} first')
#
#     # 选择每个平台对应发信bot
#     if ((isinstance(bot, Tg_Bot)) and (bot.self_id == plugin_config.splatoon3_notify_tg_bot_id)) or (
#             (isinstance(bot, Kook_Bot)) and (bot.self_id == plugin_config.splatoon3_notify_kk_bot_id)):
#         scheduler.add_job(
#             cron_job, 'interval', minutes=1, id=job_id, args=[bot],
#             misfire_grace_time=59, coalesce=True, max_instances=1
#         )
#         logger.info(f'add job {job_id}')
#
#     if bot_type == 'QQ':
#         text = f'bot {bot_type}: {bot.self_id} online ~'
#         if plugin_config.splatoon3_bot_disconnect_notify:
#             await notify_to_channel(text)
#
#
# @driver.on_bot_disconnect
# async def _(bot: Bot):
#     bot_type = 'Telegram'
#     if isinstance(bot, QQ_Bot):
#         bot_type = 'QQ'
#     elif isinstance(bot, V12_Bot):
#         bot_type = 'WeChat'
#     elif isinstance(bot, Kook_Bot):
#         bot_type = 'Kook'
#
#     text = f'bot {bot_type}: {bot.self_id} disconnect !!!!!!!!!!!!!!!!!!!'
#     if plugin_config.splatoon3_bot_disconnect_notify:
#         try:
#             await notify_to_channel(text)
#         except Exception as e:
#             logger.warning(f"{text}")
#             logger.warning(f"日志通知失败: {e}")
#
#
# @event_preprocessor
# async def tg_private_msg(bot: Tg_Bot, event: Event):
#     try:
#         user_id = event.get_user_id()
#         message = event.get_plaintext().strip()
#     except:
#         user_id = ''
#         message = ''
#
#     _event = event.dict() or {}
#     logger.debug(_event)
#     if user_id and message and 'group' not in _event.get('chat', {}).get('type', ''):
#         logger.info(f'tg_private_msg {user_id} {message}')
#
#         name = _event.get('from_', {}).get('first_name', '')
#         if _event.get('from_', {}).get('last_name', ''):
#             name += ' ' + _event.get('from_', {}).get('last_name', '')
#         if not name:
#             name = _event.get('from_', {}).get('username', '')
#
#         text = f"#tg{user_id}\n昵称:{name}\n消息:{message}"
#         try:
#             await notify_to_channel(text)
#         except Exception as e:
#             logger.warning("text")
#             logger.warning(f"日志通知失败: {e}")
#
#
# @event_preprocessor
# async def kk_private_msg(bot: Kook_Bot, event: Event):
#     try:
#         user_id = event.get_user_id()
#         message = event.get_plaintext().strip()
#     except:
#         user_id = ''
#         message = ''
#
#     if user_id == 'SYSTEM' and message == "[系统消息]":
#         return
#
#     _event = event.dict() or {}
#     logger.debug(_event)
#     if user_id and message and 'group' not in event.get_event_name():
#         logger.info(f'kk_private_msg {user_id} {message}')
#
#         name = _event.get('event', {}).get('author', {}).get('username') or ''
#         text = f"#kk{user_id}\n昵称:{name}\n消息:{message}"
#         await notify_to_channel(text)
