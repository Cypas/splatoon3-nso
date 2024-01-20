from datetime import datetime as dt, timedelta

from .battle_tools import PushStatistics
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
async def start_push(bot: Bot, event: Event):
    """开始推送"""
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, 'q群不支持该功能，该功能可在其他平台使用')
        return
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)

    user = dict_get_or_set_user_info(platform, user_id)
    if user and user.push:
        await bot_send(bot, event, '已开启推送，无需重复触发')
        return
    # push计数+1
    user = dict_get_or_set_user_info(platform, user_id, push=1, push_cnt=user.push_cnt + 1)

    # 添加定时任务
    group_id = ''
    _event = event.dict() or {}
    if _event.get('chat', {}).get('type') == 'group':
        group_id = _event['chat']['id']
    if _event.get('group_id'):
        group_id = _event['group_id']

    job_id = f'{msg_id}_push'
    logger.info(f'add push_job {job_id}')
    job_data = {
        'platform': platform,
        'user_id': user_id,
        'msg_id': msg_id,
        'this_push_cnt': 0,
        'game_name': user.game_name or "",
        'group_id': group_id,
        'job_id': job_id,
        'last_battle_id': "",
        'last_group_msg_id': "",
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
        push_latest_battle, 'interval', seconds=PUSH_INTERVAL, next_run_time=dt.now() + timedelta(seconds=3),
        id=job_id, args=[bot, event, job_data],
        misfire_grace_time=PUSH_INTERVAL - 1, coalesce=True, max_instances=1
    )
    # await push_latest_battle(bot, event, job_data)
    msg = f'Start push! check new data(battle or coop) every {PUSH_INTERVAL} seconds. /stop_push to stop'
    if isinstance(bot, (V12_Bot, Kook_Bot)):
        msg = f'开始推送战绩，每{PUSH_INTERVAL}秒钟查询一次最新数据(对战或打工)\n/stop_push 停止推送'
    await bot_send(bot, event, msg)


matcher_stop_push = on_command("stop_push", aliases={'stop', 'st', 'stp'}, priority=10, block=True)


@matcher_stop_push.handle(parameterless=[Depends(_check_session_handler)])
async def stop_push(bot: Bot, event: Event):
    """停止推送"""
    if isinstance(bot, QQ_Bot):
        await bot_send(bot, event, 'q群不支持该功能，该功能可在其他平台使用')
        return
    msg = f'Stop push!'

    logger.info(msg)
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg_id = get_msg_id(platform, user_id)
    user = dict_get_or_set_user_info(platform, user_id, push=0)

    if isinstance(bot, (V12_Bot, Kook_Bot)):
        msg = '停止推送！\n'
    if not user.stat_key:
        msg += "/set_api_key 可保存数据到 stat.ink\n(App最多可查看最近50*5场对战和50场打工,该网站可记录全部对战或打工)\n"

    job_id = f'{msg_id}_push'
    logger.info(f'remove push_job {job_id}')
    job_data = None
    try:
        r = scheduler.get_job(job_id)
        job_data = r.args[-1] or {}
        scheduler.remove_job(job_id)
    except Exception as e:
        logger.error(f"get push job data error:{e}")

    if job_data:
        push_statistics: PushStatistics = job_data.get("push_statistics")
        if push_statistics:
            msg += push_statistics.get_battle_st_msg()
            msg += push_statistics.get_coop_st_msg()

    await bot_send(bot, event, msg)


async def push_latest_battle(bot: Bot, event: Event, job_data: dict):
    """定时推送函数"""
    job_id = job_data.get('job_id')
    logger.debug(f'push_latest_battle {job_id}, {job_data}')

    platform = job_data.get('platform')
    user_id = job_data.get('user_id')
    msg_id = job_data.get('msg_id')
    push_cnt = job_data.get('this_push_cnt', 0)
    last_battle_id = job_data.get('last_battle_id')
    push_st = job_data.get('push_statistics')

    user = dict_get_or_set_user_info(platform, user_id)

    push_cnt += 1
    job_data.update({"this_push_cnt": push_cnt})
    if push_cnt * PUSH_INTERVAL % 600 == 0:
        # show log every 10 minutes
        logger.info(f'push_latest_battle: {user.game_name}, {job_id}')

    try:
        res = await get_last_battle_or_coop(platform, user_id, for_push=True)
        battle_id, _info, is_battle = res
    except Exception as e:
        logger.debug(f'push_latest_battle error: {e}')
        return

    # 如果battle_id未改变
    if last_battle_id == battle_id:
        if push_cnt * PUSH_INTERVAL / 60 > 30:
            scheduler.remove_job(job_id)
            dict_get_or_set_user_info(platform, user_id, push=0)
            msg = 'No game record for 30 minutes, stop push.'
            if isinstance(bot, (V12_Bot, Kook_Bot)):
                msg = '30分钟内没有游戏记录，停止推送。'
                if not user.stat_key:
                    msg += "\n/set_api_key 可保存数据到 stat.ink\n(App最多可查看最近50*5场对战和50场打工,该网站可记录全部对战或打工)\n"

            # 获取统计数据
            push_statistics: PushStatistics = job_data.get("push_statistics")
            if push_statistics:
                msg += push_statistics.get_battle_st_msg()
                msg += push_statistics.get_coop_st_msg()
            logger.info(f'push auto end,user：{msg_id},gamer：{user.game_name}, push cycle count:{push_cnt}')

            await bot_send(bot, event, message=msg, skip_log_cmd=True)

            msg = f"#{msg_id} {user.game_name or ''}\n 30分钟内没有游戏记录，停止推送。"
            await notify_to_channel(msg)
            return
        return
    # 获取新对战信息
    splatoon = Splatoon(platform, user.user_id, user.user_name, user.session_token, user.req_client)
    logger.info(f'{splatoon.user_db_info.db_id}, {user.game_name} get new {"battle" if is_battle else "coop"}!')
    job_data.update({"last_battle_id": battle_id})

    msg = await get_last_msg(splatoon, battle_id, _info, is_battle=is_battle, push_st=push_st)

    image_width = 720
    r = await bot_send(bot, event, message=msg, image_width=image_width, skip_log_cmd=True)
    # tg撤回上一条push的消息
    if job_data.get('group_id') and r:
        message_id = ''
        if isinstance(bot, Tg_Bot):
            message_id = r.message_id
            if job_data.get('last_group_msg_id'):
                await bot.delete_message(chat_id=r.chat.id, message_id=job_data['last_group_msg_id'])
        job_data.update({"last_group_msg_id": message_id})
