from nonebot.message import event_preprocessor
from nonebot.plugin import PluginMetadata

from .config import driver, plugin_config, Config
from .data.db_sqlite import init_db
from .data.transfer import transfer_user_db
from .handle import *
from .handle.cron import remove_all_scheduler, scheduler_controller
from .handle.send_msg import bot_send, notify_to_channel
from .s3s.splatnet_image import global_browser
from .utils import MSG_HELP_QQ, MSG_HELP_CN, MSG_HELP, BOT_VERSION
from .utils.bot import *

__plugin_meta__ = PluginMetadata(
    name="splatoon3游戏nso查询",
    description="一个基于nonebot2框架的splatoon3游戏nso数据查询插件",
    usage="发送 帮助 或 help 可查看详细指令\n",
    type="application",
    # 发布必填，当前有效类型有：`library`（为其他插件编写提供功能），`application`（向机器人用户提供功能）。
    homepage="https://github.com/Cypas/splatoon3-nso",
    # 发布必填。
    config=Config,
    supported_adapters={"~onebot.v11", "~onebot.v12", "~telegram", "~kaiheila", "~qq"},
)


@on_startswith(("/", "、"), priority=99).handle()
async def unknown_command(bot: Bot, event: Event):
    logger.info(f'unknown_command from {event.get_event_name()}')
    msg = ""
    if plugin_config.splatoon3_unknown_command_fallback_reply:
        if isinstance(bot, Tg_Bot):
            msg = "Sorry, I didn't understand that command. /help"
        elif isinstance(bot, All_BOT):
            msg = "无效指令，发送 /help 查看帮助"
        kook_black_list = plugin_config.splatoon3_unknown_command_fallback_reply_kook_black_list
        if len(kook_black_list) > 0:
            if isinstance(bot, Kook_Bot):
                server_id = 0
                if isinstance(event, Kook_CME):
                    server_id = event.extra.guild_id
                if server_id in kook_black_list:
                    msg = ""
                    logger.info("kook指定兜底黑名单服务器，不进行兜底消息提示")
        if msg:
            await bot.send(event, message=msg)


@on_command("help", aliases={"h", "帮助", "说明", "文档"}, priority=10).handle()
async def _help(bot: Bot, event: Event):
    # 帮助菜单日程插件优先模式
    if plugin_config.splatoon3_schedule_plugin_priority_mode:
        return
    else:
        if isinstance(bot, Tg_Bot):
            await bot_send(bot, event, message=MSG_HELP)
        elif isinstance(bot, QQ_Bot):
            msg = MSG_HELP_QQ
            await bot_send(bot, event, message=msg)
        elif isinstance(bot, All_BOT):
            msg = MSG_HELP_CN
            await bot_send(bot, event, message=msg)


@driver.on_startup
async def bot_on_start():
    # 检查旧数据库文件与新数据库文件是否存在
    old_db_path = f"{DIR_RESOURCE}/data.sqlite"
    new_db_path = f"{DIR_RESOURCE}/nso_data.sqlite"
    if os.path.exists(old_db_path) and not os.path.exists(new_db_path):
        # 旧数据库存在，新数据库不存在，启动转移函数
        logger.info("检测到旧版本用户数据库，将开始进行数据转移")
        transfer_user_db()
        logger.info("用户数据库转移完成")
    else:
        init_db()

    # 创建定时任务
    scheduler_controller()
    version = BOT_VERSION
    logger.info(f" bot start, version: {version} ".center(120, "-"))
    await notify_to_channel(f"bot start, version: {version}")


@driver.on_shutdown
async def bot_on_shutdown():
    version = BOT_VERSION
    logger.info(f" bot shutdown, version: {version} ".center(120, "x"))
    bots = get_bots()
    logger.info(f"bot: {bots}")


@driver.on_bot_connect
async def _(bot: Bot):
    bot_name = bot.adapter.get_name()
    logger.info(f" {bot_name} bot connect {bot.self_id} ".center(60, "-").center(90, " "))
    if bot_name == "QQ":
        text = f"bot {bot_name}: {bot.self_id} online ~"
        if plugin_config.splatoon3_bot_disconnect_notify:
            await notify_to_channel(text)


@driver.on_bot_disconnect
async def _(bot: Bot):
    bot_name = bot.adapter.get_name()
    text = f"bot {bot_name}: {bot.self_id} disconnect !!!!!!!!!!!!!!!!!!!"
    if plugin_config.splatoon3_bot_disconnect_notify:
        try:
            await notify_to_channel(text)
        except Exception as e:
            logger.warning(f"{text}")
            logger.warning(f"日志通知失败: {e}")

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
