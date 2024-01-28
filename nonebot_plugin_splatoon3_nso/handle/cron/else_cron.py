import asyncio

from .utils import cron_logger
from datetime import datetime as dt, timedelta

from ...data.data_source import dict_get_all_global_users, dict_get_or_set_user_info, model_get_all_user, \
    model_get_newest_user
from ...s3s.splatoon import Splatoon
from ...utils import get_msg_id


async def create_refresh_token_tasks():
    """创建刷新token任务"""
    cron_logger.info(f'create_refresh_token_tasks start')
    t = dt.utcnow()
    users = dict_get_all_global_users()

    # users = sorted(users, key=lambda x: x.id)
    list_user: list[tuple] = []  # 简要记录平台和user_id信息，等到具体任务内再获取user数据
    for user in users:
        list_user.append((user.platform, user.user_id))

    _pool = 50
    for i in range(0, len(list_user), _pool):
        _p_and_id_list = list_user[i:i + _pool]
        tasks = [refresh_token_task(p_and_id) for p_and_id in _p_and_id_list]
        res = await asyncio.gather(*tasks)

    cron_logger.info(f'create_set_report_tasks end: {dt.utcnow() - t}')


async def refresh_token_task(p_and_id):
    """任务：刷新token"""
    platform, user_id = p_and_id
    msg_id = get_msg_id(platform, user_id)
    try:
        u = dict_get_or_set_user_info(platform, user_id)
        if not u or not u.session_token:
            return

        splatoon = Splatoon(None, None, u)
        # 刷新token
        await splatoon.refresh_gtoken_and_bullettoken()
    except Exception as e:
        cron_logger.warning(f'refresh_token_task error: {msg_id}, {e}')
