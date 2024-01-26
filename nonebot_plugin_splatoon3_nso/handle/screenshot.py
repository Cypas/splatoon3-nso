from datetime import datetime as dt, timedelta

from .send_msg import bot_send
from .utils import _check_session_handler, get_game_sp_id_and_name, get_battle_time_or_coop_time
from ..data.data_source import dict_get_or_set_user_info
from ..s3s.splatoon import Splatoon
from ..s3s.splatnet_image import get_app_screenshot
from ..utils.bot import *

screen_shot = on_command("screen_shot", aliases={'ss'}, priority=10, block=True)


@screen_shot.handle(parameterless=[Depends(_check_session_handler)])
async def screen_shot(bot: Bot, event: Event, args: Message = CommandArg()):
    """/ss 截图指令"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    key = ""
    message = ""
    if not args.extract_plain_text().strip():
        # 没有任何参数
        await bot_send(bot, event, message="未提供任何截图参数，将截图最近对战，截图需要10秒以上时间，请稍等...")
    else:
        await bot_send(bot, event, message="截图需要10秒以上时间，请稍等...")
    if " " in args.extract_plain_text():
        # 取末尾的关键词
        key = args.extract_plain_text().split(' ')[-1].strip()
    try:
        img = await get_screenshot_image(bot, event, platform, user_id, key=key)
    except ValueError as e:
        message = "当前没有祭典投票问卷"
        img = None
    except Exception as e:
        logger.exception(e)
        message = '网络错误，请稍后再试'
        img = None
    await bot_send(bot, event, message=message, photo=img)


async def get_screenshot_image(bot, event, platform, user_id, key=None):
    """获取nso页面截图"""
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    # 测试token是否有效
    await splatoon.test_page()
    img = await get_app_screenshot(platform, user_id, key)
    return img
