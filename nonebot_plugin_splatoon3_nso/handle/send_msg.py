from .utils import send_img, send_msg
from ..utils import DIR_RESOURCE
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


async def bot_send(bot: Bot, event: Event, message: str | bytes = "", **kwargs):
    """综合发信函数，发送图片需要添加参数 photo={img_data}"""
    img_data = ''
    if message and message.strip().startswith('####'):
        width = 1000
        if 'image_width' in kwargs:
            width = kwargs.get('image_width')
        # 打工
        if 'W1 ' in message and 'duration: ' not in message:
            width = 640
        img_data = await md_to_pic(message, width=width, css_path=f'{DIR_RESOURCE}/md.css')

    if kwargs.get('photo'):
        img_data = kwargs.get('photo')

    if img_data:
        await send_img(bot, event, img_data)

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
                    message += '```'
        try:
            if isinstance(bot, QQ_Bot):
                message = message.replace('```', '').replace('\_', '_').strip().strip('`')
            await send_msg(bot, event, message)
        except Exception as e:
            logger.exception(f'bot_send error: {e}, {message}')

        # if not kwargs.get('skip_log_cmd'):
        #     await log_cmd_to_db(bot, event)
