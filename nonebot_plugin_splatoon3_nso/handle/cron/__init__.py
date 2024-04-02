import asyncio
import threading

from nonebot import require, logger

from .else_cron import create_refresh_token_tasks, clean_s3s_cache, clean_global_user_info_dict, show_dict_status, \
    init_nso_version
from .event_top import get_event_top
from .stat_ink import update_s3si_ts, sync_stat_ink
from .report import create_set_report_tasks, send_report_task
from .user_friends import create_get_user_friends_tasks
from .x_player import get_x_player

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

list_scheduler_type = []


def scheduler_controller():
    """用于创建其他scheduler的一次性函数"""

    """
    参考 https://zhuanlan.zhihu.com/p/144506204
    func：Job执行的函数
    trigger：apscheduler定义的触发器，用于确定Job的执行时间，根据设置的trigger规则，计算得到下次执行此job的时间， 满足时将会执行
    args：Job执行函数需要的位置参数
    kwargs：Job执行函数需要的关键字参数
    id：指定作业的唯一ID
    name：指定作业的名字
    misfire_grace_time：Job的延迟执行时间，单位:秒，例如Job的计划执行时间是21:00:00，但因服务重启或其他原因导致21:00:31才执行，如果设置此key为40,则该job会继续执行，否则将会丢弃此job
    coalesce：Job是否合并执行，是一个bool值。例如scheduler停止20s后重启启动，而job的触发器设置为5s执行一次，因此此job错过了4个执行时间，如果设置为是，则会合并到一次执行，否则会逐个执行
    max_instances：执行此job的最大实例数，executor执行job时，根据job的id来计算执行次数，根据设置的最大实例数来确定是否可执行
    next_run_time：Job下次的执行时间，创建Job时可以指定一个时间[datetime],不指定的话则默认根据trigger获取触发时间
    executor：apscheduler定义的执行器，job创建时设置执行器的名字，根据字符串你名字到scheduler获取到执行此job的 执行器，执行job指定的函数
    """

    def add_scheduler(_type, **kwargs):
        """添加新的的定时器"""
        global list_scheduler_type
        job_id = f"sp3_cron_job_{_type}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            list_scheduler_type.remove(_type)
        scheduler.add_job(
            id=job_id, func=cron, args=[_type],
            misfire_grace_time=60, coalesce=True, max_instances=1, **kwargs
        )
        logger.info(f"add job {job_id}")
        list_scheduler_type.append(_type)

    # parse x rank player at 2:40
    add_scheduler("parse_x_rank", trigger='cron', hour=2, minute=40)
    # 更新活动排行榜
    add_scheduler("get_event_top", trigger='cron', hour=6, minute=20)
    # 清空s3sti.ts脚本生成的缓存文件
    add_scheduler("clean_s3s_cache", trigger='cron', hour=7, minute=30)
    # set_report at 8:00
    add_scheduler("set_report", trigger='cron', hour=8, minute=0)
    # send_report at 9:00
    add_scheduler("send_report", trigger='cron', hour=9, minute=0)
    # 不同trigger下hour和minute有的带s，有的不带，就相当离谱 ###########
    # get_user_friends every 3 hours   仅为缓存内的用户提供定期获取好友信息
    add_scheduler("get_user_friends", trigger='interval', hours=3)
    # refresh_token every 1 hours 50 min   仅为缓存内的用户提供定期刷新token
    add_scheduler("refresh_token", trigger='interval', hours=1, minutes=50)
    # # update_s3si_ts 在指定时间检查脚本更新
    # add_scheduler("update_s3si_ts", trigger='cron', hour=6, minute=50)
    # sync_stat_ink 在指定时间进行同步
    add_scheduler("sync_stat_ink", trigger='cron', hour="0,2,4,6,8,10,12,14,16,18,20,22", minute=4)
    # 每周一周四清理一次公共用户字典
    add_scheduler("clean_global_user_info_dict", trigger='cron', day_of_week="mon,thu", hour=4, minute=40)
    # 每天23:59分将 NSOAPP_VERSION 和 WEB_VIEW_VERSION 置空
    add_scheduler("init_nso_version", trigger='cron', hour=23, minute=59)


async def cron(_type):
    """定时核心任务"""
    match _type:
        case "parse_x_rank":
            await get_x_player()
        case "get_event_top":
            await get_event_top()
        case "set_report":
            await create_set_report_tasks()
        case "send_report":
            await send_report_task()
        case "get_user_friends":
            await create_get_user_friends_tasks()
        case "refresh_token":
            await create_refresh_token_tasks()
        case "update_s3si_ts":
            await update_s3si_ts()
        case "sync_stat_ink":
            threading.Thread(target=asyncio.run, args=(sync_stat_ink(),)).start()
        case "clean_s3s_cache":
            await clean_s3s_cache()
        case "clean_global_user_info_dict":
            await clean_global_user_info_dict()
        case "init_nso_version":
            await init_nso_version()


def remove_all_scheduler():
    """删除全部定时任务"""
    for _type in list_scheduler_type:
        job_id = f"sp3_cron_job_{_type}"
        scheduler.remove_job(job_id)
