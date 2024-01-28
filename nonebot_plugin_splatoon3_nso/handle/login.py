import secrets
import threading
import time
from datetime import datetime as dt, timedelta

from .cron import update_s3si_ts
from .cron.stat_ink import sync_stat_ink_func
from .utils import _check_session_handler, get_event_info, get_game_sp_id
from .send_msg import bot_send, notify_to_channel
from ..config import plugin_config
from ..data.data_source import dict_get_or_set_user_info, model_delete_user, global_user_info_dict, \
    model_get_or_set_user
from ..s3s.iksm import S3S
from ..s3s.splatoon import Splatoon
from ..utils import get_msg_id, DIR_RESOURCE, get_or_init_client
from ..utils.bot import *

MSG_PRIVATE = "请私信机器人完成登录操作"
global_login_status_dict: dict = {}
global_login_code_dict: dict = {}

matcher_login_in = on_command("login", priority=10, block=True)


@matcher_login_in.handle()
async def login_in(bot: Bot, event: Event, matcher: Matcher):
    """登录"""
    if isinstance(bot, QQ_Bot):
        kk_guild_id = plugin_config.splatoon3_kk_guild_id
        msg = f"Q群当前无法登录nso，请至其他平台完成登录后获取绑定码\nKook服务器id：{kk_guild_id}"
        await bot_send(bot, event, msg)
        await matcher.finish()
        return

    if 'group' in event.get_event_name():
        if isinstance(bot, (V12_Bot, Kook_Bot, QQ_Bot)):
            await matcher_login_in.finish(MSG_PRIVATE)
            return
        await matcher_login_in.finish(MSG_PRIVATE, reply_message=True)
        await matcher.finish()
        return

    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    user = dict_get_or_set_user_info(platform, user_id)
    if user and user.session_token:
        msg = '用户已经登录\n如需重新登录或切换账号请继续下面操作\n登出或清空账号数据 /clear_db_info'
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
    url, auth_code_verifier = await s3s.log_in()
    global_login_status_dict.update(
        {msg_id: {"auth_code_verifier": auth_code_verifier,
                  "s3s": s3s,
                  "create_time": dt.now().strftime("%Y-%m-%d %H:%M:%S")}})
    logger.info(f'get login url: {url}')
    logger.info(f'auth_code_verifier: {auth_code_verifier}')
    if url:
        msg = ''
        if isinstance(bot, Tg_Bot):
            msg = f'''
Navigate to this URL in your browser:
{url}
Log in, right click the "Select this account" button, copy the link address, and paste below. (Valid for 2 minutes)
            '''
        elif isinstance(bot, (V11_Bot, V12_Bot, Kook_Bot)):
            msg = f'''在浏览器中打开下面链接（移动端复制链接至其他浏览器）,
登陆后，在显示红色的选择此人按钮时，右键红色按钮(手机端长按复制)
复制链接后发送给机器人 (两分钟内有效！)
'''
        if msg:
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

    err_msg = '登录失败，请 /login 重试, 复制新链接'
    if (not text) or (len(text) < 500) or (not text.startswith('npf')) or (auth_code_verifier is None):
        logger.info(err_msg)
        await bot.send(event, message=err_msg)
        return

    session_token = await s3s.login_in_2(use_account_url=text, auth_code_verifier=auth_code_verifier)
    if not session_token or session_token == 'skip':
        logger.info(err_msg)
        await bot.send(event, message=err_msg)
        return
    logger.info(f'session_token: {session_token}')

    event_info = await get_event_info(bot, event)
    user_name = event_info.get('username', "")
    # 更新数据库
    user = dict_get_or_set_user_info(platform, user_id, session_token=session_token, user_name=user_name)
    # 刷新token
    await bot.send(event, message="登录中，正在刷新token，请等待大约10s")
    req_client = get_or_init_client(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    await splatoon.refresh_gtoken_and_bullettoken()

    msg = f"""
Login success! Bot now can get your splatoon3 data from SplatNet.
/me - show your info
/last - show the latest battle or coop
/start_push - start push mode
/set_api_key - set stat.ink api_key, bot will sync your data to stat.ink
"""
    if isinstance(bot, (V11_Bot, V12_Bot, Kook_Bot)):
        msg = f"""登录成功！机器人现在可以从App获取你的数据。
如果希望在q群使用nso查询，请发送
/get_login_code
获取一次性跨平台绑定码

常用指令:
/me - 显示你的信息
/friends - 显示在线的喷喷好友
/last - 显示最近一场对战或打工
/report - 获取昨天或指定日期的日报数据
/start_push - 开启推送模式
/set_api_key - 设置 api_key, 同步数据到 https://stat.ink
更多完整nso操作指令:
https://docs.qq.com/sheet/DUkZHRWtCUkR0d2Nr?tab=BB08J2
"""
    await bot.send(event, message=msg)
    global_login_status_dict.pop(msg_id)
    logger.info(f'login success:{msg_id} {user_name}')

    # 取最近对战数据获取game_sp_id
    res_battle = await splatoon.get_recent_battles()
    b_info = res_battle['data']['latestBattleHistories']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]
    game_sp_id = get_game_sp_id(b_info['player']['id'])
    user = dict_get_or_set_user_info(platform, user_id, game_sp_id=game_sp_id)
    _msg = f'new_login_user: 会话昵称:{user_name}\nns_player_code:{game_sp_id}\n{session_token}'
    await notify_to_channel(_msg)


@on_command("clear_db_info", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def clear_db_info(bot: Bot, event: Event):
    """清空账号数据"""
    if 'group' in event.get_event_name():
        await bot_send(bot, event, '请私聊机器人', parse_mode='Markdown')
        return

    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    model_delete_user(platform, user_id)
    global_user_info_dict.pop(msg_id)

    msg = "All your data cleared! 已清空账号数据!"
    logger.info(msg)
    await bot_send(bot, event, message=msg)


@on_command("get_login_code", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def get_login_code(bot: Bot, event: Event):
    """获取绑定码"""
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, '暂不支持')
        return
    if 'group' in event.get_event_name():
        await bot_send(bot, event, '请私信机器人')
        return

    platform = bot.adapter.get_name()
    user_id = event.get_user_id()

    # 生成一次性 code
    login_code = secrets.token_urlsafe(20)
    login_code_info = {"platform": platform, "user_id": user_id, "create_time": int(time.time())}
    global_login_code_dict.update({login_code: login_code_info})
    msg = f'请在Q群内艾特机器人并发送下行指令完成跨平台绑定\n该绑定码为有效期10分钟的一次性的随机字符串，不用担心别人重复使用'
    await bot_send(bot, event, message=msg)
    await bot.send(event, message='我是分割线'.center(20, '-'))
    await bot_send(bot, event, message=f'/set_login {login_code}')


@on_command("set_login", priority=10, block=True).handle()
async def set_login_code(bot: QQ_Bot, event: Event):
    """绑定账号"""
    if isinstance(bot, Kook_Bot):
        await bot_send(bot, event, '暂不支持')
        return

    login_code = event.get_plaintext().strip()[10:].strip()
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)

    login_code_info = global_login_code_dict.get(login_code)

    if not login_code_info:
        await bot_send(bot, event, 'code错误，账号绑定失败')
        return
    create_time = login_code_info.get("create_time")
    if int(time.time()) - create_time > 600:
        await bot_send(bot, event, 'code已过期，请重新生成')
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
        await bot_send(bot, event, '旧用户数据不存在，账号绑定失败')
        return

    # 复制信息至新账号
    user = dict_get_or_set_user_info(platform, user_id, session_token=old_user.session_token, g_token=old_user.g_token,
                                     bullet_token=old_user.bullet_token,
                                     access_token=old_user.access_token, game_name=old_user.game_name,
                                     game_sp_id=old_user.game_sp_id, stat_key=old_user.stat_key)

    # 清空 code
    global_login_code_dict.pop(login_code)

    msg = f"""登录成功！机器人现在可以从App获取你的数据。
/me - 显示你的信息
/friends - 显示在线的喷喷好友
/last - 显示最近一场对战或打工
/report - 喷喷早报
"""
    await bot_send(bot, event, msg)

    logger.info(f'set_login success: {msg_id},old user is {old_msg_id}')

    await notify_to_channel(f'绑定QQ成功: {msg_id}, 旧用户为{old_msg_id}')


matcher_set_api_key = on_command("set_api_key", priority=10, block=True)


@matcher_set_api_key.handle(parameterless=[Depends(_check_session_handler)])
async def set_api_key(bot: Bot, event: Event):
    """设置stat.ink的api_key"""
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, 'Q群不支持该命令，请从其他平台进行设置')
        return
    if 'group' in event.get_event_name():
        await matcher_set_api_key.finish(MSG_PRIVATE)
        return

    msg = '''Please copy you api_key from https://stat.ink/profile then paste below'''
    if isinstance(bot, (V11_Bot, V12_Bot, Kook_Bot)):
        msg = '''请从 https://stat.ink/profile 页面复制你的 api_key 后,将key直接发送给机器人
注册stat.ink账号后，无需其他操作，设置api_key
机器人会同步你的数据到 stat.ink (App最多保存最近50*5场对战和50场打工数据,该网站可记录全部对战或打工)
        '''
    await bot_send(bot, event, message=msg)


@on_regex("^[A-Za-z0-9_-]{30,}", priority=10, block=True).handle()
async def get_set_api_key(bot: Bot, event: Event):
    """stat api key匹配"""
    if 'group' in event.get_event_name():
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

    msg = f'''set_api_key success, bot will check every 2 hours and post your data to stat.ink.
first sync will be in minutes.
    '''
    if isinstance(bot, (V11_Bot, V12_Bot, Kook_Bot)):
        msg = f'''设置成功，机器人会检查一次并同步你的数据到 stat.ink
/api_notify 关 - 设置关闭推送通知
        '''
    await bot_send(bot, event, message=msg)

    update_s3si_ts()
    db_user = model_get_or_set_user(platform, user_id)
    threading.Thread(target=sync_stat_ink_func, args=(db_user,)).start()


@on_command("sync_now", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def sync_now(bot: Bot, event: Event):
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, '暂不支持')
        return
    if 'group' in event.get_event_name():
        await bot_send(bot, event, MSG_PRIVATE)
        return

    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    if not (user and user.session_token and user.stat_key):
        msg = 'Please set api_key first, /set_api_key'
        if isinstance(bot, (V11_Bot, V12_Bot, Kook_Bot)):
            msg = '请先设置 api_key, /set_api_key'
        await bot_send(bot, event, msg)
        return

    update_s3si_ts()
    msg = "战绩手动同步任务已开始，请稍等..."
    db_user = model_get_or_set_user(platform, user_id)
    if db_user:
        await bot_send(bot, event, msg)
        await sync_stat_ink_func(db_user)
    return
