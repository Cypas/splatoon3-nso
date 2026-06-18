from urllib.parse import quote

from nonebot import on_message, on_startswith, Bot, logger, on_command, on_notice
from nonebot.adapters.qq.message import Attachment
from nonebot.internal.rule import Rule
from nonebot.rule import to_me, is_type


from .send_msg import bot_send, notify_to_private, bot_send_new_user_added_md, send_msg
from .utils import write_unknown_command
from .qq_md import get_qq_face_md
from ..utils.utils import MSG_HELP, MSG_HELP_QQ, MSG_HELP_CN
from ..utils import get_msg_id
from ..config import plugin_config
from ..utils.bot import *

@on_message(rule=to_me(), priority=97, block=True).handle()
@on_startswith(("/", "、"), priority=99, block=True).handle()
async def unknown_command(bot: Bot, event: Event, matcher: Matcher):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    plain_text = event.get_message().extract_plain_text().strip()
    logger.info(f'unknown_command from {event.get_event_name()}')
    msg = ""
    if plugin_config.splatoon3_unknown_command_fallback_reply:
        if isinstance(bot, Tg_Bot):
            msg = "Sorry, I didn't understand that command. /help"
        elif isinstance(bot, QQ_Bot):
            if plugin_config.splatoon3_qq_md_mode:
                if isinstance(event, QQ_C2CME):
                    user_id = ""
                title = "小鱿鱿没有这个功能指令，点击下方按钮试试吧！"
                msg = f"更多指令可以点击我头像，或是最新版qq在聊天框输入/ 唤起机器人菜单"
                await bot_send_new_user_added_md(bot, event, user_id, title=title, msg=msg)
            else:
                msg = "小鱿鱿没有这个功能指令，请发送/help 查看帮助\n或在qq消息框输入/后，手动选择bot指令"
                await send_msg(bot, event, msg=msg)
        elif isinstance(bot, All_BOT):
            msg = "小鱿鱿没有这个功能指令，请发送/help 查看帮助"
        kook_black_list = plugin_config.splatoon3_unknown_command_fallback_reply_kook_black_list
        if len(kook_black_list) > 0:
            if isinstance(bot, Kook_Bot):
                server_id = 0
                if isinstance(event, Kook_CME):
                    server_id = event.extra.guild_id
                if server_id in kook_black_list:
                    msg = ""
                    logger.info("kook指定兜底黑名单服务器，不进行兜底消息提示")
        if msg and not isinstance(bot, QQ_Bot):
            await send_msg(bot, event, msg=msg)
        # 写未知命令
        write_unknown_command(msg_id, plain_text)
        await matcher.finish()


@on_message(rule=is_type(QQ_C2CME), priority=96, block=True).handle()
async def c2c_unknown_command(bot: Bot, event: Event, matcher: Matcher):
    """为qq c2c任何未匹配文本进行兜底"""
    plain_text = event.get_message().extract_plain_text().strip()
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    logger.info(f'unknown_command from {event.get_event_name()}')

    # 写未知命令
    write_unknown_command(msg_id, plain_text)
    if isinstance(bot, QQ_Bot) and plugin_config.splatoon3_qq_md_mode:
        if isinstance(event, QQ_C2CME):
            user_id = ""
        title = "小鱿鱿没有这个功能指令，点击下方按钮试试吧！"
        msg = (f"小鱿鱿可以提供splatoon3游戏日程，随机武器，配装等基础查询功能\n"
               f"在登录nso后还可以提供实时查询对战/打工战绩，好友状态，观星导出等nso查询功能\n"
               f"更多指令可以点击我头像，或是最新版qq在聊天框输入/ 唤起机器人菜单")
        await bot_send_new_user_added_md(bot, event, user_id, title=title, msg=msg)
    else:
        msg = "小鱿鱿没有这个功能指令，请发送/help 查看帮助\n或在qq消息框输入/后，手动选择bot指令"
        await bot_send(bot, event, msg)

# rule函数
async def qq_is_my_face_img(event: Event) -> bool:
    plain_text = event.get_message().extract_plain_text()
    return True if "faceType=6" in plain_text else False


@on_message(rule=is_type(QQ_C2CME) & Rule(qq_is_my_face_img), priority=50, block=True).handle()
async def c2c_face_image_command(bot: Bot, event: Event, matcher: Matcher):
    """为qq c2c 下表情导出"""
    massage = event.get_message()
    # massage结构为 [Text(type='text', data={'text': '<faceType=6,faceId="0",ext="eyJ0ZXh0IjoiIn0=">'}),Attachment(type='image', data={'url': "https: //multimedia.nt.qq.com.cn"})]  list列表内填充了两个不同的obj类型
    logger.info(f'检测为qq表情，进行图片转发')
    if len(massage) >= 2:
        attachment: Attachment = massage[1]
        url = attachment.data.get("url") or ""
        if url:
            encoded_url = quote(url, safe=':/?&=')
            try:
                await bot.send(event, message=await get_qq_face_md(user_id="", url=encoded_url))
            except QQ_ActionFailed as e:
                logger.error(f"qq转发表情失败,res:{e.message},url:{encoded_url}")
                await matcher.finish("qq表情解析失败了，请再发一次")
            except Exception as e:
                logger.error(f"qq转发表情失败:url:{encoded_url},error:{e}")
            matcher.stop_propagation()


@on_command("help", aliases={"h", "帮助", "说明", "文档"}, priority=10).handle()
async def nso_help(bot: Bot, event: Event):
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


@on_notice(rule=is_type(QQ_GAddEvent, QQ_FAddEvent), priority=10, block=True).handle()
async def bot_added_event(bot: QQ_Bot, event: Event, matcher: Matcher):
    """qq机器人被个人添加/被群添加"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    title = "你好，我是小鱿鱿bot"
    msg = (f"我可以提供splatoon3游戏日程，随机武器，配装等基础查询功能\n"
           f"在登录nso后还可以提供实时查询对战/打工战绩，好友状态，观星导出等nso查询功能\n"
           f"更多指令可以点击我头像，或是最新版qq在聊天框输入/ 唤起机器人菜单\n")

    if plugin_config.splatoon3_qq_md_mode:
        if isinstance(event, QQ_FAddEvent):
            user_id = ""
        await bot_send_new_user_added_md(bot, event, user_id, title=title, msg=msg)
    else:
        msg = f"{title}\n\n{msg}"
        await bot_send(bot, event, msg)

