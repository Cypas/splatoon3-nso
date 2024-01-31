import io

from PIL import Image
from nonebot.adapters.qq import AuditException, ActionFailed

from .qq_md import last_md, login_md
from ..utils import DIR_RESOURCE, get_msg_id, get_time_now_china_str
from ..utils.bot import *
from ..config import plugin_config

require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import md_to_pic


async def report_notify_to_channel(platform: str, user_id: str, msg: str, _type='job'):
    """stat同步 和 report 通知到频道"""
    # 通知标题
    msg_id = get_msg_id(platform, user_id)
    title = f"#{msg_id}"
    # 去掉msg原有的md格式
    msg = msg.replace("```\n", "")
    msg = msg.replace("```", "")

    msg = f"{title}\n{msg}"

    # 消息过滤处理
    if platform == "Telegram":
        if "stat.ink" in msg:
            msg = msg.replace('Exported', '#Exported')
        else:
            if "早报" in msg:
                msg = '#report\n' + msg
    elif platform == "OneBot V12":
        msg = msg.replace('```', '').strip()
    elif platform == "Kaiheila":
        pass
    await notify_to_channel(msg, _type=_type)


async def cron_notify_to_channel(msg: str, _type='job'):
    """任务处理通知到频道"""
    title = f"#cron_notify\n"
    title += get_time_now_china_str()
    title += "\n"
    await notify_to_channel(f"{title}{msg}", _type)


notify_tg_bot_id = plugin_config.splatoon3_notify_tg_bot_id
tg_c_chat_id = plugin_config.splatoon3_tg_channel_msg_chat_id
tg_c_job_id = plugin_config.splatoon3_tg_channel_job_chat_id

notify_kk_bot_id = plugin_config.splatoon3_notify_kk_bot_id
kk_c_chat_id = plugin_config.splatoon3_kk_channel_msg_chat_id
kk_c_job_id = plugin_config.splatoon3_kk_channel_job_chat_id


async def notify_to_channel(_msg, _type='msg'):
    """消息通知至频道"""
    channel_id = ""
    # log to telegram
    if _type == 'msg':
        channel_id = tg_c_chat_id
    elif _type == 'job':
        channel_id = tg_c_job_id

    # log to kook
    if _type == 'msg':
        channel_id = kk_c_chat_id
    elif _type == 'job':
        channel_id = kk_c_job_id

    bots = get_bots()
    # 推送至tg
    if notify_tg_bot_id and channel_id:
        tg_bot = bots.get(notify_tg_bot_id)
        if tg_bot:
            try:
                _msg = f"```\n{_msg}```"
                await tg_bot.send_message(channel_id, _msg)
            except Exception as e:
                logger.warning(f'tg频道通知消息失败: {e}')

    # 推送至kook
    if notify_kk_bot_id and channel_id:
        kook_bot = bots.get(notify_kk_bot_id)
        if kook_bot:
            try:
                _msg = f"```\n{_msg}```"
                await kook_bot.send_channel_msg(channel_id=channel_id,
                                                message=Kook_MsgSeg.KMarkdown(_msg))
            except Exception as e:
                logger.warning(f'kook频道通知消息失败: {e}')


async def notify_to_private(platform: str, user_id: str, msg: str):
    """通知至私聊"""
    # 排除QQ平台
    if platform == "QQ":
        return

    bot = None
    bots = get_bots()
    # tg平台
    if platform == "Telegram" and notify_tg_bot_id:
        tg_bot = bots.get(notify_tg_bot_id)
        if tg_bot:
            bot = tg_bot

    # kook平台
    elif platform == "Kaiheila" and notify_kk_bot_id:
        kook_bot = bots.get(notify_kk_bot_id)
        if kook_bot:
            bot = kook_bot

    if bot:
        # 发送私信
        await send_private_msg(bot, user_id, msg)


async def bot_send(bot: Bot, event: Event, message: str | bytes = "", **kwargs):
    """综合发信函数，发送图片需要添加参数 photo={img_data}"""
    img_data = ''
    if message and message.strip().startswith('####'):
        width = 1000
        if 'image_width' in kwargs:
            width = kwargs.get('image_width')
        # 打工
        if 'W1 ' in message and 'duration: ' not in message:
            width = 680
        img_data = await md_to_pic(message, width=width, css_path=f'{DIR_RESOURCE}/md.css')

    if kwargs.get('photo'):
        img_data = kwargs.get('photo')

    if img_data:
        await send_msg(bot, event, img_data)

        # if not kwargs.get('skip_log_cmd'):
        #     await log_cmd_to_db(bot, event)
    else:
        # 下面为文字消息
        if isinstance(bot, (Tg_Bot, Kook_Bot, QQ_Bot)):
            if 'group' in event.get_event_name() or isinstance(bot, QQ_Bot):
                # /me 截断
                if '开放' in message and ': (+' not in message:
                    coop_lst = message.split('2022-')[-1].split('2023-')[-1].strip().split('\n')
                    message = message.split('2022-')[0].split('2023-')[0].strip() + '\n'
                    for l in coop_lst:
                        if '打工次数' in l or '头目鲑鱼' in l:
                            message += '\n' + l
                    # message += '```'
        try:
            if isinstance(bot, QQ_Bot):
                message = message.replace('```', '').replace('\_', '_').strip().strip('`')
            await send_msg(bot, event, message)
        except Exception as e:
            logger.exception(f'bot_send error: {e}, {message}')

        # if not kwargs.get('skip_log_cmd'):
        #     await log_cmd_to_db(bot, event)


async def bot_send_last_md(bot: Bot, event: Event, message: str, user_id: str, image_width=None):
    """发送qq md消息"""
    img_data = ''
    width = 1000
    if message and message.strip().startswith('####'):
        if image_width:
            width = image_width
        # 打工
        if 'W1 ' in message and 'duration: ' not in message:
            width = 680
        img_data = await md_to_pic(message, width=width, css_path=f'{DIR_RESOURCE}/md.css')

    if img_data:
        # 通过pillow库获取图片宽高数据
        image = Image.open(io.BytesIO(img_data))
        width, height = image.size
        image.close()
        # 获取图片url
        url = await get_image_url(img_data)
        qq_msg = last_md(user_id, image_size=(width, height), url=url)
        await bot.send(event, qq_msg)


async def bot_send_login_md(bot: Bot, event: Event, user_id: str):
    """发送login md消息"""
    qq_msg = login_md(user_id)
    await bot.send(event, qq_msg)


async def send_msg(bot: Bot, event: Event, msg: str | bytes):
    """公用send_msg"""
    # 指定回复模式
    reply_mode = plugin_config.splatoon3_reply_mode

    if isinstance(msg, str):
        # 文字消息
        if isinstance(bot, V11_Bot):
            await bot.send(event, message=V11_MsgSeg.text(msg), reply_message=reply_mode)
        elif isinstance(bot, V12_Bot):
            await bot.send(event, message=V12_MsgSeg.text(msg), reply_message=reply_mode)
        elif isinstance(bot, Tg_Bot):
            if reply_mode:
                await bot.send(event, msg, reply_to_message_id=event.dict().get("message_id"))
            else:
                await bot.send(event, msg)
        elif isinstance(bot, Kook_Bot):
            await bot.send(event, message=Kook_MsgSeg.text(msg), reply_sender=reply_mode)
        elif isinstance(bot, QQ_Bot):
            await bot.send(event, message=QQ_MsgSeg.text(msg))

    elif isinstance(msg, bytes):
        # 图片
        img = msg
        if isinstance(bot, V11_Bot):
            try:
                await bot.send(event, message=V11_MsgSeg.image(file=img, cache=False), reply_message=reply_mode)
            except Exception as e:
                logger.warning(f"QQBot send error: {e}")
        elif isinstance(bot, V12_Bot):
            # onebot12协议需要先上传文件获取file_id后才能发送图片
            try:
                resp = await bot.upload_file(type="data", name="temp.png", data=img)
                file_id = resp["file_id"]
                if file_id:
                    await bot.send(event, message=V12_MsgSeg.image(file_id=file_id), reply_message=reply_mode)
            except Exception as e:
                logger.warning(f"QQBot send error: {e}")
        elif isinstance(bot, Tg_Bot):
            if reply_mode:
                await bot.send(event, Tg_File.photo(img), reply_to_message_id=event.dict().get("message_id"))
            else:
                await bot.send(event, Tg_File.photo(img))
        elif isinstance(bot, Kook_Bot):
            url = await bot.upload_file(img)
            await bot.send(event, Kook_MsgSeg.image(url), reply_sender=reply_mode)
        elif isinstance(bot, QQ_Bot):
            if not isinstance(event, GroupAtMessageCreateEvent):
                await bot.send(event, message=QQ_MsgSeg.file_image(img))
            else:
                url = await get_image_url(img)
                if url:
                    await bot.send(event, message=QQ_MsgSeg.image(url))


async def get_image_url(img: bytes) -> str:
    """通过kook获取图片url"""
    bots = nonebot.get_bots()
    kook_bot = bots.get(notify_kk_bot_id)
    url = ""
    if kook_bot is not None:
        # 使用kook的接口传图片
        url = await kook_bot.upload_file(img)
    return url


async def send_channel_msg(bot: Bot, source_id, msg: str | bytes):
    """公用发送频道消息"""
    if isinstance(msg, str):
        # 文字消息
        if isinstance(bot, Kook_Bot):
            await bot.send_channel_msg(channel_id=source_id, message=Kook_MsgSeg.text(msg))
        elif isinstance(bot, QQ_Bot):
            try:
                await bot.send_to_channel(channel_id=source_id, message=QQ_MsgSeg.text(msg))
            except AuditException as e:
                logger.warning(f"主动消息审核结果为{e.__dict__}")
            except ActionFailed as e:
                logger.warning(f"主动消息发送失败，api操作结果为{e.__dict__}")
        elif isinstance(bot, Tg_Bot):
            await bot.send_message(chat_id=source_id, text=msg)
    elif isinstance(msg, bytes):
        # 图片
        img = msg
        if isinstance(bot, Kook_Bot):
            url = await bot.upload_file(img)
            await bot.send_channel_msg(channel_id=source_id, message=Kook_MsgSeg.image(url))
        elif isinstance(bot, QQ_Bot):
            try:
                await bot.send_to_channel(channel_id=source_id, message=QQ_MsgSeg.file_image(img))
            except AuditException as e:
                logger.warning(f"主动消息审核结果为{e.__dict__}")
            except ActionFailed as e:
                logger.warning(f"主动消息发送失败，api操作结果为{e.__dict__}")
        elif isinstance(bot, Tg_Bot):
            await bot.send_photo(source_id, img)


async def send_private_msg(bot: Bot, source_id, msg: str | bytes, event=None):
    """公用发送私聊消息"""
    if isinstance(msg, str):
        # 文字消息
        if isinstance(bot, Kook_Bot):
            await bot.send_private_msg(user_id=source_id, message=Kook_MsgSeg.text(msg))
        elif isinstance(bot, QQ_Bot):
            try:
                if event:
                    await bot.send_to_dms(guild_id=event.guild_id, message=msg, msg_id=event.id)
            except AuditException as e:
                logger.warning(f"主动消息审核结果为{e.__dict__}")
            except ActionFailed as e:
                logger.warning(f"主动消息发送失败，api操作结果为{e.__dict__}")
        elif isinstance(bot, Tg_Bot):
            await bot.send_message(chat_id=source_id, text=msg)

    elif isinstance(msg, bytes):
        # 图片
        img = msg
        if isinstance(bot, Kook_Bot):
            url = await bot.upload_file(img)
            await bot.send_private_msg(user_id=source_id, message=Kook_MsgSeg.image(url))
        elif isinstance(bot, QQ_Bot):
            try:
                await bot.send_to_dms(guild_id=event.guild_id, message=QQ_MsgSeg.file_image(img), msg_id=event.id)
            except AuditException as e:
                logger.warning(f"主动消息审核结果为{e.__dict__}")
            except ActionFailed as e:
                logger.warning(f"主动消息发送失败，api操作结果为{e.__dict__}")
        elif isinstance(bot, Tg_Bot):
            await bot.send_photo(source_id, img)
