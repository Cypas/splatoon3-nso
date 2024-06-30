from datetime import datetime as dt, timedelta

from .b_or_c_tools import PushStatistics
from .utils import _check_session_handler, PUSH_INTERVAL
from .send_msg import bot_send, notify_to_channel
from .last import get_last_battle_or_coop, get_last_msg
from ..s3s.splatoon import Splatoon
from ..data.data_source import dict_get_or_set_user_info
from ..utils import get_msg_id
from ..utils.bot import *

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

matcher_start_push = on_command("start_push", aliases={'sp', 'push', 'start'}, priority=10, block=True)


@matcher_start_push.handle(parameterless=[Depends(_check_session_handler)])
async def start_push(bot: Bot, event: Event, args: Message = CommandArg()):
    """开始推送"""
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, "QQ平台不支持该功能，该功能可在其他平台使用")
        return
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)

    user = dict_get_or_set_user_info(platform, user_id)
    if user and user.push:
        await bot_send(bot, event, "已开启推送，无需重复触发")
        return
    # push计数+1
    user = dict_get_or_set_user_info(platform, user_id, push=1, push_cnt=user.push_cnt + 1)

    # 检查push的条件
    get_battle = False
    get_coop = False
    get_screenshot = False
    mask = False
    fast = False
    cmd_message = args.extract_plain_text().strip()
    # 筛选参数
    if cmd_message:
        cmd_lst = cmd_message.split(" ")
        if "b" in cmd_lst or "battle" in cmd_lst:
            get_battle = True
        if "c" in cmd_lst or "coop" in cmd_lst:
            get_coop = True
        if get_battle and get_coop:
            get_battle = False
            get_coop = False
        if "ss" in cmd_lst or "screenshot" in cmd_lst:
            get_screenshot = True
        if "m" in cmd_lst or "mask" in cmd_lst:
            mask = True
        if "f" in cmd_lst or "fast" in cmd_lst:
            fast = True
    filters = {"get_battle": get_battle,
               "get_coop": get_coop,
               "get_screenshot": get_screenshot,
               "mask": mask,
               "fast": fast,
               }
    # 看来源是否是群聊
    channel_id = ""
    if isinstance(event, Tg_CME):
        channel_id = event.chat.id
    elif isinstance(event, Kook_CME):
        channel_id = event.group_id

    # 轮询间隔时间
    if not fast:
        push_interval = PUSH_INTERVAL * 4  # 增加到1min
    else:
        push_interval = PUSH_INTERVAL
    # 添加定时任务
    job_id = f"{msg_id}_push"
    logger.info(f"add push_job {job_id}")
    job_data = {
        'bot': bot,
        'event': event,
        'platform': platform,
        'user_id': user_id,
        'msg_id': msg_id,
        'this_push_cnt': 0,
        'error_push_cnt': 0,
        'match_push_cnt': 0,
        'game_name': user.game_name or "",
        'job_id': job_id,
        'last_battle_id': "",
        'channel_id': channel_id,
        'last_channel_msg_id': "",
        'push_interval': push_interval,
        'push_statistics': PushStatistics(),
    }

    """
    func：Job执行的函数
    trigger：apscheduler定义的触发器，用于确定Job的执行时间，根据设置的trigger规则，计算得到下次执行此job的时间， 满足时将会执行
    args：Job执行函数需要的位置参数
    kwargs：Job执行函数需要的关键字参数
    id：指定作业的唯一ID
    name：指定作业的名字
    misfire_grace_time：Job的延迟执行时间，例如Job的计划执行时间是21:00:00，但因服务重启或其他原因导致21:00:31才执行，如果设置此key为40,则该job会继续执行，否则将会丢弃此job
    coalesce：Job是否合并执行，是一个bool值。例如scheduler停止20s后重启启动，而job的触发器设置为5s执行一次，因此此job错过了4个执行时间，如果设置为是，则会合并到一次执行，否则会逐个执行
    max_instances：执行此job的最大实例数，executor执行job时，根据job的id来计算执行次数，根据设置的最大实例数来确定是否可执行
    next_run_time：Job下次的执行时间，创建Job时可以指定一个时间[datetime],不指定的话则默认根据trigger获取触发时间
    executor：apscheduler定义的执行器，job创建时设置执行器的名字，根据字符串你名字到scheduler获取到执行此job的 执行器，执行job指定的函数
    """
    scheduler.add_job(
        push_latest_battle, 'interval', seconds=push_interval, next_run_time=dt.now() + timedelta(seconds=3),
        id=job_id, args=[bot, event, job_data, filters],
        misfire_grace_time=push_interval - 1, coalesce=True, max_instances=1
    )
    if isinstance(bot, Tg_Bot):
        msg = f'Start push! check new data(battle or coop) every {push_interval} seconds. /stop_push to stop'
    elif isinstance(bot, All_BOT):
        filters_str1 = ""
        if get_screenshot:
            filters_str1 += "截图"
        if mask:
            filters_str1 += "打码"

        filters_str2 = "对战或打工"
        if get_battle:
            filters_str2 = "对战"
        if get_coop:
            filters_str2 = "打工"
        msg = f'开始推送{filters_str1}战绩，每{push_interval}秒查询一次最新 {filters_str2} 数据\n/stop_push 停止推送'
    await bot_send(bot, event, msg)


matcher_stop_push = on_command("stop_push", aliases={'stp', 'st', 'stop'}, priority=10, block=True)


@matcher_stop_push.handle(parameterless=[Depends(_check_session_handler)])
async def stop_push(bot: Bot, event: Event):
    """停止推送"""
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, 'QQ平台不支持该功能，该功能可在其他平台使用')
        return

    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    user = dict_get_or_set_user_info(platform, user_id, push=0)

    _, _, st_msg, push_time_minute = close_push(platform, user_id)
    if isinstance(bot, Tg_Bot):
        msg = f"Stop push!"
    elif isinstance(bot, All_BOT):
        msg = f"停止推送！推送持续 {push_time_minute}分钟\n"
    if not user.stat_key and user.push_cnt <= 10:
        msg += "/set_stat_key 可保存数据到 stat.ink\n(App最多可查看最近50*5场对战和50场打工,该网站可记录全部对战或打工,也可用于武器/地图/模式/胜率的战绩分析)\n"

    msg += st_msg

    await bot_send(bot, event, msg)


async def push_latest_battle(bot: Bot, event: Event, job_data: dict, filters: dict):
    """定时推送函数"""
    job_id = job_data.get('job_id')
    logger.debug(f'push_latest_battle {job_id}, {job_data}')
    # job_data
    platform = job_data.get('platform')
    user_id = job_data.get('user_id')
    msg_id = job_data.get('msg_id')
    push_cnt = job_data.get('this_push_cnt', 0)
    error_push_cnt = job_data.get('error_push_cnt', 0)
    last_battle_id = job_data.get('last_battle_id')
    push_interval = job_data.get('push_interval')
    push_statistics: PushStatistics = job_data.get("push_statistics")
    # filters
    get_battle = filters["get_battle"]
    get_coop = filters["get_coop"]
    get_screenshot = filters["get_screenshot"]
    mask = filters["mask"]

    user = dict_get_or_set_user_info(platform, user_id)

    push_cnt += 1
    job_data.update({"this_push_cnt": push_cnt})
    # if push_cnt * PUSH_INTERVAL % 600 == 0:
    #     # show log every 10 minutes
    #     logger.info(f'push_latest_battle: {user.game_name}, {job_id}')

    splatoon = Splatoon(bot, event, user)
    try:
        # 多次连续请求报错时，结束push推送
        if error_push_cnt >= 3:
            # 关闭定时，更新push状态，发送统计
            dict_get_or_set_user_info(platform, user_id, push=0)
            msg = ""

            # 获取统计数据
            _, _, st_msg, push_time_minute = close_push(platform, user_id)
            if isinstance(bot, All_BOT):
                msg = f"服务器连续多次请求报错，停止推送，bot可能遇到了网络问题，请加 新人导航 频道内的q群联系主人，本次推送持续 {push_time_minute}分钟\n\n"
            msg += st_msg

            logger.info(
                f"push too much error,auto end,user：{msg_id:>3},gamer：{user.game_name:>7}, push {push_time_minute} minutes")

            await bot_send(bot, event, message=msg, skip_log_cmd=True)
            msg = f"#{msg_id} {user.game_name or ''}\n 连续多次请求报错，停止推送，推送持续 {push_time_minute}分钟"
            await notify_to_channel(msg)
            return

        # 获取对战或打工数据
        res = await get_last_battle_or_coop(bot, event, for_push=True, get_battle=get_battle,
                                            get_coop=get_coop,
                                            get_screenshot=get_screenshot, mask=mask)
        battle_id, _info, is_battle, is_playing = res

        # # 第一次push时不处理最后一次超过20分钟的记录
        # if not last_battle_id and not is_playing:
        #     job_data.update({"last_battle_id": battle_id})
        #     return

        # 如果battle_id未改变  或  last_battle_id长时间未赋值
        if last_battle_id == battle_id or (push_cnt > 2 and not last_battle_id):
            if not is_playing and push_cnt * push_interval / 60 > 20:
                # 关闭定时，更新push状态，发送统计
                dict_get_or_set_user_info(platform, user_id, push=0)
                msg = 'No game record for 20 minutes, stop push.'

                # 获取统计数据
                _, _, st_msg, push_time_minute = close_push(platform, user_id)
                if isinstance(bot, All_BOT):
                    msg = f"20分钟内没有游戏记录，停止推送，本次推送持续 {push_time_minute}分钟, {job_data.get('match_push_cnt') or 0}次对局\n"
                    if not user.stat_key and user.push_cnt <= 10:
                        msg += "/set_stat_key 可保存数据到 stat.ink\n(App最多可查看最近50*5场对战和50场打工,该网站可记录全部对战或打工,也可用于武器/地图/模式/胜率的战绩分析)\n"
                msg += st_msg

                logger.info(
                    f"push auto end,user：{msg_id:>3},gamer：{user.game_name:>7}, push {push_time_minute} minutes")

                await bot_send(bot, event, message=msg, skip_log_cmd=True)
                msg = f"#{msg_id} {user.game_name or ''}\n 20分钟内没有游戏记录，停止推送，推送持续 {push_time_minute}分钟"
                await notify_to_channel(msg)
                return
            return

        # 获取新对战信息
        logger.info(f'{splatoon.user_db_info.db_id}, {user.game_name} get new {"battle" if is_battle else "coop"}!')
        job_data.update({"last_battle_id": battle_id})

        msg = await get_last_msg(splatoon, battle_id, _info, is_battle=is_battle, push_statistics=push_statistics,
                                 get_screenshot=get_screenshot, mask=mask)

        image_width = 680
        r = await bot_send(bot, event, message=msg, image_width=image_width, skip_log_cmd=True)

        # tg撤回上一条push的消息
        if job_data.get('channel_id') and r:
            if isinstance(bot, Tg_Bot):
                if job_data.get('last_channel_msg_id'):
                    await bot.delete_message(chat_id=r.chat.id, message_id=job_data['last_channel_msg_id'])
            message_id = r.message_id
            job_data.update({"last_channel_msg_id": message_id})

        # 连续error计数置0
        job_data.update({"error_push_cnt": 0})
        # 比赛计数+1
        job_data['match_push_cnt'] += 1

    except Exception as e:
        logger.warning(f'push_latest_battle error: {e}')
        error_push_cnt += 1
        job_data.update({"error_push_cnt": error_push_cnt})
        return
    finally:
        # 关闭连接池
        await splatoon.req_client.close()


def close_push(platform, user_id):
    """关闭push"""
    msg_id = get_msg_id(platform, user_id)
    job_id = f'{msg_id}_push'
    logger.info(f'remove push_job {job_id}')
    job_data = None
    msg = ""
    push_time_minute = 0
    bot = None
    event = None
    try:
        r = scheduler.get_job(job_id)
        job_data = r.args[2] or {}
        scheduler.remove_job(job_id)
    except Exception as e:
        logger.error(f"get push job data error:{e}")

    if job_data:
        push_statistics: PushStatistics = job_data.get("push_statistics")
        push_interval = job_data.get("push_interval")
        bot = job_data.get("bot")
        event = job_data.get("event")
        if push_statistics:
            msg += push_statistics.get_battle_st_msg()
            msg += push_statistics.get_coop_st_msg()
        # 计算推送持续时间
        push_cnt = job_data.get('this_push_cnt', 0)
        push_time_minute: float = float(push_cnt * push_interval) / 60
    return bot, event, msg, push_time_minute
