from urllib.parse import quote

from nonebot import on_message, on_startswith, Bot, logger, on_command, on_notice
from nonebot.adapters.qq import AtMessageCreateEvent
from nonebot.adapters.qq.models.qq import Attachment
from nonebot.internal.rule import Rule
from nonebot.rule import to_me, is_type

from .send_msg import bot_send, notify_to_private, bot_send_new_user_added_md, send_msg, bot_send_full_message_check_md
from .utils import write_unknown_command, write_full_message_check_text
from .qq_md import get_qq_face_md
from ..utils.utils import MSG_HELP, MSG_HELP_QQ, MSG_HELP_CN, get_file_bytes
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
async def qq_is_my_face_img(event: QQ_C2CME) -> bool:
    content = event.content
    # print(f"原始事件:{vars(event)}")
    # print(f"检测到消息为:{event.get_message()}")
    # print(f"原文为:{content}")
    return True if "faceType=6" in content else False


@on_message(rule=is_type(QQ_C2CME) & Rule(qq_is_my_face_img), priority=50, block=True).handle()
async def c2c_face_image_command(bot: Bot, event: QQ_C2CME, matcher: Matcher):
    """为qq c2c 下表情导出"""

    # event 结构为 {
    #     'id': 'ROBOT1.0_CD5reDe6wXBjyPdovfSjDv0qVlTsNBp.OJf8H1s7tyRwFC-JCOgfeiYG6plZ6y7xzd7-qrDE-u1E1QuGl4z5-b3ngGb.Wl-sLP-ZQpRmBmM!',
    #     'content': '<faceType=6,faceId="0",ext="eyJ0ZXh0IjoiIn0=">', 'timestamp': '2026-06-22T14:02:34+08:00',
    #     'mentions': None,
    #     'attachments': [
    #         Attachment(content_type='image/jpeg', filename='3911FCFFAACD45620CBDE8161B165B0D.jpg', height=1046,
    #                    width=1280, size=64779,
    #                    url='https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=EhTUarirpH_GQ1ZLDlJKcuKeoAZFVRiL-gMg_goov4mym5aalQMyBHByb2RQgLsvWhAydtVIqI3J_VBRMlwGTisCegKzEIIBAmd6&rkey=CAISONPsN0nSR8aLO020SY3nAJIQpX_oXsuWglftjuhR4SrfQTTwd0IVKehC8d0JlUtOu-Ptk_QwUZSC&spec=0')],
    #     'message_scene': _QQMessageScene(ext=['msg_idx=REFIDX_FAAw8RYjG0RZNz252cCrWctG81ovPjw88HwjHppK6Gc='],
    #                                      source='default'), 'message_type': 0, 'msg_idx': None, 'msg_elements': None,
    #     'event_id': 'C2C_MESSAGE_CREATE:ulgodeslgjoanlo4mhfjdiamgzu1prcuhr2cwss3znfuohchhcigml0xmisoz2', 'to_me': True,
    #     'reply': None,
    #     'author': FriendAuthor(id='5A66317A1334DA9762183C77C8325549', user_openid='5A66317A1334DA9762183C77C8325549',
    #                            union_openid='5A66317A1334DA9762183C77C8325549', username='')
    # }

    # https: // multimedia.nt.qq.com.cn / download?appid = 1406 & fileid = EhRZ1aazpiEU7jSS7 - kzQnUKdiua5hjougUg_gooqLu8jJWalQMyBHByb2RQgLsvWhAd9YOTh3fYkSs3whoQVam9egLgx4IBAmd6 & rkey = CAISONPsN0nSR8aLMX - RTY2t47uxVuYatHhDbwYRFPmzvY7BWnzEkHHd9QbXN4rJzNPy1eh9dfDoMH_o & spec = 0
    #
    # https: // multimedia.nt.qq.com.cn / download?appid = 1406 & fileid = EhTUarirpH_GQ1ZLDlJKcuKeoAZFVRiL - gMg_gooi6Xa6JualQMyBHByb2RQgLsvWhDtbDFeB_l0Q1aA69uNoPsKegKt_oIBAmd6 & rkey = CAQSODOc_jvbthUjz - iE5Xqfe - 6
    # RD2nT2QOC1e4rrarmESS4KyMKB4PMgpyXpFOQ0OyjdyV - 85
    # W63Jlu & spec = 0
    # message结构为 [Text(type='text', data={'text': '<faceType=6,faceId="0",ext="eyJ0ZXh0IjoiIn0=">'}),Attachment(type='image', data={'url': "https: //multimedia.nt.qq.com.cn"})]  list列表内填充了两个不同的obj类型
    logger.info(f'检测为qq表情，进行图片转发')
    attachment: Attachment = event.attachments[0]
    url = attachment.url
    if url:
        encoded_url = quote(url, safe=':/?&=')
        # 防止两个_内容_嵌在md里被识别为斜体内容
        encoded_url = encoded_url.replace("_", r"%5F")
        h = attachment.height
        w = attachment.width
        try:
            md = await get_qq_face_md(user_id="", url=encoded_url, w=w, h=h)
            # print(md)
            await bot.send(event, message=md)
        except QQ_ActionFailed as e:
            logger.error(f"qq转发表情失败,res:{e.message},url:{encoded_url}")
            await matcher.finish("qq表情解析失败了，请再发一次")
        except Exception as e:
            logger.error(f"qq转发表情失败:url:{encoded_url},error:{e}")
        matcher.stop_propagation()


@on_command("help", aliases={"h", "帮助", "说明", "文档", "幫助", "說明", "文檔"}, priority=10).handle()
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


@on_command("免艾特申请", aliases={'免艾特申請'}, priority=10, block=True).handle()
async def full_message_help(bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()):
    """全量消息申请菜单"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    f_config = plugin_config.splatoon3_full_message_config
    if not f_config.enabled:
        await matcher.finish("免艾特触发bot功能未开启")
    if type(event) == QQ_GME:
        await matcher.finish("本群已开启免艾特触发bot，无需重复开启")
    if not isinstance(event, QQ_GATME):
        await matcher.finish("该功能仅支持qq群内使用")
    # qq群id编码
    group_id = event.group_openid
    url_template = ("https://club.vip.qq.com/transfer?open_kuikly_info=%7B%22page_name%22%3A%20%22"
                    "ai_group_service_agreement_pop_page%22%2C%22"
                    "groupCode%22%3A{qq_group_id}%2C%22botUin%22%3A{bot_qq}%2C%22"
                    "botUid%22%3A%22{bot_uid}%22%2C%22screen%22%3A1%7D")

    bot_qq = f_config.bot_qq
    bot_uid = f_config.bot_uid
    plain_text = args.extract_plain_text().strip()
    if not plain_text or not plain_text.isdigit():
        await matcher.finish("申请命令后面请加上qq群号，如/免艾特申请 1234567890")
    qq_group_id = plain_text
    check_url = url_template.format(qq_group_id=qq_group_id, bot_qq=bot_qq, bot_uid=bot_uid)
    # print(check_url)

    write_full_message_check_text(group_id=group_id, qq_group_id=qq_group_id, msg_id=msg_id)
    msg = get_file_bytes("full_message_help2.jpg")
    await bot_send_full_message_check_md(bot, event, message=msg, check_url=check_url, user_id=user_id)
