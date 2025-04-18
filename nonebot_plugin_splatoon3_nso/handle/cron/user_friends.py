import asyncio

from .utils import cron_logger
from datetime import datetime as dt

from ..send_msg import cron_notify_to_channel
from ...data.data_source import dict_get_all_global_users, dict_get_or_set_user_info, model_set_user_friend
from ...s3s.splatoon import Splatoon
from ...utils import get_msg_id, convert_td


async def create_get_user_friends_tasks():
    """创建获取好友列表任务"""
    cron_msg = f"create_get_user_friends_tasks start"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("get_user_friends", "start")

    t = dt.utcnow()
    users = dict_get_all_global_users()

    # users = sorted(users, key=lambda x: x.id)
    list_user: list[tuple] = []  # 简要记录平台和user_id信息，等到具体任务内再获取user数据
    for user in users:
        list_user.append((user.platform, user.user_id))

    _pool = 5
    semaphore = asyncio.Semaphore(_pool)  # 并发控制
    counters = {'friends_count': 0}

    async def process_single_user(p_and_id):
        async with semaphore:
            try:
                f_list = await get_friends_task(p_and_id)
                if f_list:
                    model_set_user_friend(f_list)
                    counters['friends_count'] += len(f_list)
            except Exception as e:
                cron_logger.error(f"Failed to process {p_and_id}: {str(e)}")

    # 动态提交所有任务（不再分批）
    tasks = [process_single_user(p_and_id) for p_and_id in list_user]
    await asyncio.gather(*tasks)

    cron_logger.info(f"get all friends count: {counters['friends_count']}")
    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = f"create_get_user_friends_tasks end: {str_time}\nget friends: {counters['friends_count']}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("get_user_friends", "end", f"耗时:{str_time}\n获取好友: {counters['friends_count']}")


async def get_friends_task(p_and_id):
    """任务：get_friends"""
    platform, user_id = p_and_id
    msg_id = get_msg_id(platform, user_id)
    u = dict_get_or_set_user_info(platform, user_id)
    if not u or not u.session_token:
        return

    splatoon = Splatoon(None, None, u)
    try:
        # 获取好友
        res = await splatoon.get_friends()
        if not res:
            cron_logger.warning(f'get_friends error: {msg_id}, {u.user_name}')
            return

        f_list = []
        for f in res['data']['friends']['nodes']:
            if f.get('onlineState') == 'OFFLINE':
                continue

            friend_id = f['id']
            player_name = f.get('playerName') or ''
            nickname = f.get('nickname') or ''
            cron_logger.debug(f'get_friend: {msg_id},{u.game_name}--sp:{player_name} ,ns:{nickname}')
            user_icon = f['userIcon']['url']
            f_list.append((user_id, friend_id, player_name, nickname, user_icon))

        return f_list

    except Exception as e:
        cron_logger.warning(f'refresh_token_task error: {msg_id}, {e}')
