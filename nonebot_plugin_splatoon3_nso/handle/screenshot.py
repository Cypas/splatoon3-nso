from .send_msg import bot_send
from .utils import _check_session_handler
from ..data.data_source import dict_get_or_set_user_info
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
    if not cmd:
        # 没有任何参数
        await matcher.finish(message="未提供任何页面关键词,全部页面关键词如下: 个人穿搭 好友 最近 涂地 蛮颓 x赛 活动 私房 武器 徽章 打工记录 击倒数量 打工 鲑鱼跑 祭典 祭典问卷\n如/ss 击倒数量")
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
            message="页面关键词无效,全部页面关键词如下: 个人穿搭 好友 最近 涂地 蛮颓 x赛 活动 私房 武器 徽章 打工记录 击倒数量 打工 鲑鱼跑 祭典 祭典问卷\n如/ss 击倒数量")

    try:
        # 此处message为bytes
        message = await get_screenshot_image(bot, event, platform, user_id, key=key)
    except ValueError as e:
        message = "当前没有祭典投票问卷"
    except Exception as e:
        logger.exception(e)
        message = "bot网络错误，请稍后再试"
    await bot_send(bot, event, message=message)


async def get_screenshot_image(bot, event, platform, user_id, key=None):
    """获取nso页面截图"""
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    msg_id = get_msg_id(platform, user_id)

    # 只有第一次使用ss时需要测试token是否有效，后续加入了token定时维护便不再需要测试
    context = global_dict_ss_user.get(msg_id)
    if not context:
        # 测试token是否有效
        await splatoon.test_page()
    img = await get_app_screenshot(platform, user_id, key)
    # 关闭连接池
    await splatoon.req_client.close()
    return img
