from nonebot.adapters.qq import AuditException, ActionFailed

from ..utils import DIR_RESOURCE, get_msg_id
from ..utils.bot import *
from ..config import plugin_config

require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import md_to_pic


async def notify_to_channel(_msg, _type='msg', **kwargs):
    # log to telegram
    notify_tg_bot_id = kwargs.get('tg_bot_id', None) or plugin_config.splatoon3_notify_tg_bot_id
    tg_channel_chat_id = kwargs.get('tg_chat_id', None) or plugin_config.splatoon3_tg_channel_msg_chat_id
    if _type == 'job':
        tg_channel_chat_id = kwargs.get('tg_chat_id', None) or plugin_config.splatoon3_tg_channel_job_chat_id

    # log to kook
    notify_kk_bot_id = kwargs.get('kook_bot_id', None) or plugin_config.splatoon3_notify_kk_bot_id
    kk_channel_chat_id = kwargs.get('kook_chat_id', None) or plugin_config.splatoon3_kk_channel_msg_chat_id
    if _type == 'job':
        kk_channel_chat_id = kwargs.get('kook_chat_id', None) or plugin_config.splatoon3_kk_channel_job_chat_id
    for bot in get_bots().values():
        if isinstance(bot, Tg_Bot):
            try:
                # 推送至tg
                if notify_tg_bot_id and tg_channel_chat_id and (bot.self_id == notify_tg_bot_id):
                    await bot.send_message(tg_channel_chat_id, _msg)
            except Exception as e:
                logger.warning(f'tg频道通知消息失败: {e}')

        if isinstance(bot, Kook_Bot):
            try:
                # 推送至kook
                if notify_kk_bot_id and kk_channel_chat_id and (bot.self_id == notify_kk_bot_id):
                    await bot.send_channel_msg(channel_id=kk_channel_chat_id,
                                               message=Kook_MsgSeg.KMarkdown(f"```\n{_msg}```"))
            except Exception as e:
                logger.warning(f'kook频道通知消息失败: {e}')


async def notify_to_private(platform: str, user_id: str, msg: str):
    """通知至私聊"""
    # 排除QQ平台
    if platform == "QQ":
        return
    # tg_bot
    notify_tg_bot_id = plugin_config.splatoon3_notify_tg_bot_id
    # kook_bot
    notify_kk_bot_id = plugin_config.splatoon3_notify_kk_bot_id
    # 通知标题
    msg_id = get_msg_id(platform, user_id)
    title = f'#{msg_id} \n'
    bot = None
    for _bot in get_bots().values():
        # 确定平台
        if _bot.adapter.get_name() == platform:
            # 确认发信bot
            if isinstance(_bot, Tg_Bot) and notify_tg_bot_id and _bot.self_id == notify_tg_bot_id:
                bot = _bot
                break
            if isinstance(_bot, Kook_Bot) and notify_kk_bot_id and _bot.self_id == notify_kk_bot_id:
                bot = _bot
                break

    # 消息过滤处理
    if isinstance(bot, Tg_Bot):
        if 'stat.ink' in msg:
            msg = msg.replace('Exported', '#Exported')
        else:
            if '早报' in msg:
                msg = '#report\n' + msg
    elif isinstance(bot, V12_Bot):
        msg = msg.replace('```', '').strip()
    elif isinstance(bot, Kook_Bot):
        pass

    if bot:
        # 发送私信
        await send_private_msg(bot, user_id, msg)
        # 通知到频道
        await notify_to_channel(title + msg, _type='job')


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
                # 目前q群只支持url图片，得想办法上传图片获取url
                kook_bot = None
                bots = nonebot.get_bots()
                for k, b in bots.items():
                    if isinstance(b, Kook_Bot):
                        kook_bot = b
                        break
                if kook_bot is not None:
                    # 使用kook的接口传图片
                    url = await kook_bot.upload_file(img)
                    await bot.send(event, message=QQ_MsgSeg.image(url))


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
