import asyncio
import secrets
import threading
import time
from datetime import datetime as dt

from .cron import update_s3si_ts
from .cron.stat_ink import sync_stat_ink_func
from .utils import _check_session_handler, get_event_info, get_game_sp_id
from .send_msg import bot_send, notify_to_channel, bot_send_login_md
from ..config import plugin_config
from ..data.data_source import dict_get_or_set_user_info, model_delete_user, global_user_info_dict, \
    model_get_or_set_user
from ..s3s.iksm import S3S
from ..s3s.splatoon import Splatoon
from ..utils import get_msg_id, DIR_RESOURCE
from ..utils.bot import *

MSG_PRIVATE = "该指令需要私信机器人才能使用"
global_login_status_dict: dict = {}
global_login_code_dict: dict = {}

matcher_login_in = on_command("login", priority=10, block=True)


@matcher_login_in.handle()
async def login_in(bot: Bot, event: Event, matcher: Matcher):
    """登录"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()

    # 只有q平台 且 q群才发md
    if isinstance(bot, QQ_Bot):
        if isinstance(event, QQ_GME) and plugin_config.splatoon3_qq_md_mode:
            # 发送md
            await bot_send_login_md(bot, event, user_id)
        else:
            msg = "QQ平台当前无法完成nso登录流程，请至其他平台完成登录后使用/getlc命令获取绑定码\n" \
                  f"Kook服务器id：{plugin_config.splatoon3_kk_guild_id}"
            await bot_send(bot, event, msg)

        await matcher.finish()

    if isinstance(event, All_Group_Message):
        await matcher.finish(MSG_PRIVATE)

    msg_id = get_msg_id(platform, user_id)
    user = dict_get_or_set_user_info(platform, user_id)
    if user and user.session_token:
        msg = "用户已经登录nso\n" \
              "如需重新登录或绑定账号请继续下面操作\n" \
              "/clear_db_info 登出并清空账号数据\n" \
              "/get_login_code 获取绑定码以绑定其他平台bot账号"
        await bot_send(bot, event, msg)
        await matcher.finish()

    img_path = f'{DIR_RESOURCE}/sp3bot-login.gif'
    if isinstance(bot, Tg_Bot):
        try:
            logger.debug(f'img_path: {img_path}')
            await bot.send(event, Tg_File.animation(img_path))
        except Exception as e:
            logger.error(f'login error: {e}')

    s3s = S3S(platform, user_id)
    try:
        url, auth_code_verifier = await s3s.login_in()
    except Exception as e:
        logger.error(f'get login_in url error: {e}')
        await matcher.finish("bot网络错误，请稍后重试")
    global_login_status_dict.update(
        {msg_id: {"auth_code_verifier": auth_code_verifier,
                  "s3s": s3s,
                  "create_time": dt.now().strftime("%Y-%m-%d %H:%M:%S")}})
    logger.info(f'get login url: {url}')
    logger.info(f'auth_code_verifier: {auth_code_verifier}')
    if url:
        msg = ''
        if isinstance(bot, Tg_Bot):
            msg = "Navigate to this URL in your browser:\n" \
                  f"{url}"
            await bot.send(event, message=msg)

        elif isinstance(bot, All_BOT):
            msg = "风险告知:小鱿鱿所使用的nso查询本质上为第三方nso软件，此类第三方调用可能会导致nso鱿鱼圈被封禁，目前未观察到游戏连带被禁的情况。(要怪请去怪乌贼研究所)\n" \
                  "若继续完成以下登录流程，则视为您已知晓此风险并继续使用nso查询\n\n"
            msg += "登录流程: 在浏览器中打开下面链接（移动端复制链接至其他浏览器,\n" \
                   "登陆后，在显示红色的选择此人按钮时，右键红色按钮(手机端长按复制)\n" \
                   "复制其链接后发送给机器人，链接是一串npf开头的文本(两分钟内有效！)"
            await bot.send(event, message=msg)
            await bot.send(event, message='我是分割线'.center(20, '-'))
            await bot.send(event, message=url)


matcher_login_in_2 = on_startswith("npf", priority=10)


@matcher_login_in_2.handle()
async def login_in_2(bot: Bot, event: Event):
    text = event.get_plaintext()
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    # 查找用户登录字典
    user_login_status = global_login_status_dict.get(msg_id)
    if user_login_status is None:
        return

    auth_code_verifier = user_login_status.get("auth_code_verifier")
    s3s: S3S = user_login_status.get("s3s")

    err_msg = "登录失败，请 /login 重试, 并在浏览器打开bot新发给你的登录链接，在重新完成登录后，复制按钮的新链接给我，链接是一串npf开头的文本"
    if (not text) or (len(text) < 500) or (not text.startswith('npf')) or (auth_code_verifier is None):
        logger.info(err_msg)
        # 登录失败直接销毁用户等待字典
        global_login_status_dict.pop(msg_id)
        await bot.send(event, message=err_msg)
        return

    session_token = await s3s.login_in_2(use_account_url=text, auth_code_verifier=auth_code_verifier)
    if not session_token or session_token == 'skip':
        logger.info(err_msg)
        await bot.send(event, message=err_msg)
        return
    logger.info(f'session_token: {session_token}')

    event_info = await get_event_info(bot, event)
    user_name = event_info.get('user_name', "")
    # 更新数据库
    user = dict_get_or_set_user_info(platform, user_id, session_token=session_token, user_name=user_name,
                                     user_agreement=1)
    # 刷新token
    await bot.send(event, message="登录中，正在刷新token，请等待大约10s")
    splatoon = Splatoon(bot, event, user)
    await splatoon.refresh_gtoken_and_bullettoken()

    if isinstance(bot, Tg_Bot):
        msg = "Login success! Bot now can get your splatoon3 data from SplatNet.\n" \
              "/me - show your info\n" \
              "/last - show the latest battle or coop\n" \
              "/start_push - start push mode\n" \
              "/set_stat_key - set stat.ink api_key, bot will sync your data to stat.ink"
    elif isinstance(bot, All_BOT):
        msg = "登录成功！机器人现在可以从App获取你的数据。\n" \
              "如果希望在q群使用nso查询，请发送\n" \
              "/get_login_code\n" \
              "获取一次性跨平台绑定码\n" \
              "\n" \
              "常用指令:\n" \
              "/me - 显示你的信息\n" \
              "/friends - 显示在线的喷喷好友\n" \
              "/last - 显示最近一场对战或打工\n" \
              "/report - 获取昨天或指定日期的日报数据\n" \
              "/start_push - 开启推送模式\n" \
              "/set_stat_key - 设置 api_key, 同步数据到 https://stat.ink\n" \
              "更多完整nso操作指令:\n"

        if plugin_config.splatoon3_schedule_plugin_priority_mode:
            # 日程插件帮助优先模式
            msg += "/nso帮助"
        else:
            msg += "https://docs.qq.com/sheet/DUkZHRWtCUkR0d2Nr?tab=BB08J2"
    await bot.send(event, message=msg)
    global_login_status_dict.pop(msg_id)
    logger.info(f'login success:{msg_id} {user_name}')

    # 取最近对战数据获取game_sp_id
    res_battle = await splatoon.get_recent_battles()
    b_info = res_battle['data']['latestBattleHistories']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]
    game_sp_id = get_game_sp_id(b_info['player']['id'])
    user = dict_get_or_set_user_info(platform, user_id, game_sp_id=game_sp_id)
    # 登录完成后从用户池删除该残缺对象(缺少部分数据库的值，重新init后就正常了)
    global_user_info_dict.pop(msg_id)
    _msg = f'new_login_user: 会话昵称:{user_name}\nns_player_code:{game_sp_id}\n{session_token}'

    # 关闭连接池
    await splatoon.req_client.close()
    await notify_to_channel(_msg)


@on_command("clear_db_info", priority=10, block=True).handle()
async def clear_db_info(bot: Bot, event: Event):
    """清空账号数据"""
    platform = bot.adapter.get_name()
    if isinstance(event, All_Group_Message_Without_QQ_G):
        await bot_send(bot, event, "请私聊机器人")
        return

    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    model_delete_user(platform, user_id)
    if msg_id in global_user_info_dict:
        global_user_info_dict.pop(msg_id)

    msg = "All your data cleared! 已清空账号数据!"
    logger.info(msg)
    await bot_send(bot, event, message=msg)


@on_command("get_login_code", aliases={'getlogincode', 'glc', 'getlc'}, priority=10, block=True).handle(
    parameterless=[Depends(_check_session_handler)])
async def get_login_code(bot: Bot, event: Event):
    """获取绑定码"""
    if isinstance(event, QQ_GME):
        await bot_send(bot, event, "q群暂不支持此功能")
        return
    if isinstance(event, All_Group_Message):
        await bot_send(bot, event, MSG_PRIVATE)
        return

    platform = bot.adapter.get_name()
    user_id = event.get_user_id()

    # 生成一次性 code
    login_code = secrets.token_urlsafe(20)
    login_code_info = {"platform": platform, "user_id": user_id, "create_time": int(time.time())}
    global_login_code_dict.update({login_code: login_code_info})
    msg = f"请在其他平台艾特机器人并发送下行指令完成跨平台绑定\n该绑定码为有效期10分钟的一次性的随机字符串，不用担心别人重复使用"
    await bot_send(bot, event, message=msg)
    await bot.send(event, message="我是分割线".center(20, "-"))
    await bot_send(bot, event, message=f"/set_login {login_code}")


@on_command("set_login", priority=10, block=True).handle()
async def set_login_code(bot: Bot, event: Event):
    """绑定账号"""

    login_code = event.get_plaintext().strip()[10:].strip()
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)

    login_code_info = global_login_code_dict.get(login_code)

    if not login_code_info:
        await bot_send(bot, event, "code错误，账号绑定失败")
        return
    create_time = login_code_info.get("create_time")
    if int(time.time()) - create_time > 600:
        await bot_send(bot, event, "code已过期，请重新生成")
        global_login_code_dict.pop(login_code)
        return

    # 查找旧账号信息
    old_platform = login_code_info.get("platform")
    old_user_id = login_code_info.get("user_id")
    old_msg_id = get_msg_id(old_platform, old_user_id)
    if old_platform and old_user_id:
        old_user = dict_get_or_set_user_info(old_platform, old_user_id)
    else:
        old_user = None
    if not old_user:
        await bot_send(bot, event, "旧用户数据不存在，账号绑定失败")
        return

    # 复制信息至新账号
    user = dict_get_or_set_user_info(platform, user_id, session_token=old_user.session_token, g_token=old_user.g_token,
                                     bullet_token=old_user.bullet_token, access_token=old_user.access_token,
                                     game_name=old_user.game_name, game_sp_id=old_user.game_sp_id,
                                     stat_key=old_user.stat_key, user_agreement=old_user.user_agreement)

    # 清空 code
    global_login_code_dict.pop(login_code)

    msg = "登录成功！机器人现在可以从App获取你的数据。\n" \
          "/me - 显示你的信息\n" \
          "/friends - 显示在线的喷喷好友\n" \
          "/last - 显示最近一场对战或打工\n" \
          "/report - 喷喷早报\n"
    if plugin_config.splatoon3_schedule_plugin_priority_mode:
        # 日程插件帮助优先模式
        msg += "更多完整nso操作指令:\n/nso帮助"

    await bot_send(bot, event, msg)

    logger.info(f'set_login success: {msg_id},old user is {old_msg_id}')

    await notify_to_channel(f"绑定账号成功: {msg_id}, 旧用户为{old_msg_id},{old_user.user_name}")


matcher_set_api_key = on_command("set_stat_key", aliases={"set_api_key"}, priority=10, block=True)


@matcher_set_api_key.handle(parameterless=[Depends(_check_session_handler)])
async def set_api_key(bot: Bot, event: Event):
    """设置stat.ink的api_key"""
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, "QQ平台暂不支持该命令，请从其他平台进行设置")
        return
    if isinstance(event, All_Group_Message):
        await matcher_set_api_key.finish(MSG_PRIVATE)
        return
    if isinstance(bot, Tg_Bot):
        msg = "Please copy you api_key from https://stat.ink/profile then paste below"
    elif isinstance(bot, All_BOT):
        msg = "请从 https://stat.ink/profile 页面复制你的 api_key 后,将key直接发送给机器人\n" \
              "注册stat.ink账号后，无需其他操作，设置api_key后，\n" \
              "机器人会同步你的数据到 stat.ink (App最多保存最近50*5场对战和50场打工数据,该网站可记录全部对战或打工,也可用于武器/地图/模式/胜率的战绩分析)"
    await bot_send(bot, event, message=msg)


@on_regex("^[A-Za-z0-9_-]{30,}", priority=10, block=True).handle()
async def get_set_api_key(bot: Bot, event: Event):
    """stat api key匹配"""
    if isinstance(event, All_Group_Message):
        return
    stat_key = event.get_plaintext().strip()
    if len(stat_key) != 43:
        await matcher_set_api_key.finish("key错误,请重新复制key后发送给我")
        return

    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    user = dict_get_or_set_user_info(platform, user_id, stat_key=stat_key)
    logger.info(f'{msg_id} set_api_key: {stat_key}')

    if isinstance(bot, Tg_Bot):
        msg = "set_api_key success, bot will check every 2 hours and post your data to stat.ink.\n" \
              "first sync will be in minutes."
    elif isinstance(bot, All_BOT):
        msg = f"设置成功，bot将开始同步你当前的对战及打工数据到 stat.ink，并后续每2h进行一次同步"
    await bot_send(bot, event, message=msg)

    await update_s3si_ts()
    db_user = model_get_or_set_user(platform, user_id)
    threading.Thread(target=asyncio.run, args=(sync_stat_ink_func(db_user),)).start()


@on_command("sync_now", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def sync_now(bot: Bot, event: Event):
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, "QQ平台暂不支持该命令，请在其他平台使用该命令")
        return
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    if not (user and user.session_token and user.stat_key):
        if isinstance(bot, Tg_Bot):
            msg = "Please set api_key first, /set_stat_key"
        elif isinstance(bot, All_BOT):
            msg = "请先设置 stat.ink网站的api_key, 指令:/set_stat_key"
        await bot_send(bot, event, msg)
        return

    await update_s3si_ts()
    msg = "战绩手动同步任务已开始，请稍等..."
    db_user = model_get_or_set_user(platform, user_id)
    if db_user:
        await bot_send(bot, event, msg)
        threading.Thread(target=asyncio.run, args=(sync_stat_ink_func(db_user),)).start()
    return
