from .send_msg import bot_send
from .utils import _check_session_handler
from ..data.data_source import dict_get_or_set_user_info
from ..s3s.iksm import S3S
from ..s3s.splatoon import Splatoon
from ..s3s.splatnet_image import get_app_screenshot, ss_url_trans, global_dict_ss_user
from ..s3s.utils import SPLATNET3_URL
from ..utils import get_msg_id
from ..utils.bot import *

matcher_screen_shot = on_command("screen_shot", aliases={'ss'}, priority=10, block=True)


@matcher_screen_shot.handle(parameterless=[Depends(_check_session_handler)])
async def screen_shot(bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()):
    """/ss 截图指令"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    key = ""
    message = ""
    cmd = args.extract_plain_text().strip()
    all_keys = f"个人穿搭 好友 最近 涂地 蛮颓 x赛 活动 私房 武器进度 武器分数 徽章 打工记录 击倒数量 打工 鲑鱼跑 祭典 祭典问卷\n如/ss 击倒数量"
    if not cmd:
        # 没有任何参数
        await matcher.finish(message=f"未提供任何页面关键词,全部页面关键词如下: {all_keys}")
    else:
        await bot_send(bot, event, message="正在截图nso页面，请稍等...")
    if " " in cmd:
        # 取末尾的关键词
        key = cmd.split(' ')[-1].strip()
    else:
        key = cmd

    url = ""
    # 判断是否有效页面参数
    for k, v in ss_url_trans.items():
        if k in key:
            url = f"{SPLATNET3_URL}/{v}"
            break
    if not url:
        await matcher.finish(
            message=f"页面关键词无效,全部页面关键词如下: {all_keys}")

    try:
        # 此处message为bytes
        message = await get_screenshot_image(bot, event, platform, user_id, key=key)
    except ValueError as e:
        if "text not found" in str(e):
            message = "当前没有祭典投票问卷"
        if "get_screenshot_image error" in str(e):
            message = "token刷新失败，请稍后再试"
    except Exception as e:
        logger.exception(e)
        message = "bot网络错误，请稍后再试"
    await bot_send(bot, event, message=message)


async def get_screenshot_image(bot, event, platform, user_id, key=None):
    """获取nso页面截图"""
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg_id = get_msg_id(platform, user_id)

    if not S3S.is_jwt_token_valid(splatoon.g_token):
        # 发送等待文本
        await bot_send(splatoon.bot, splatoon.event,
                       "本次nso截图需要刷新token，请求耗时会比平时更长一些，请稍等...")
        suss = await splatoon.refresh_gtoken_and_bullettoken()
        if not suss:
            return "bot网络错误，请稍后再试"

    img = await get_app_screenshot(splatoon, key)
    return img
