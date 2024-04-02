import asyncio
import json
import os
import shutil

from .utils import cron_logger
from datetime import datetime as dt

from ..send_msg import cron_notify_to_channel
from ...s3s.splatnet_image import global_dict_ss_user
from ...utils.utils import DIR_RESOURCE
from ...utils.http import global_client_dict, global_cron_client_dict
from ...data.data_source import dict_get_all_global_users, dict_get_or_set_user_info, dict_clear_user_info_dict, \
    global_user_info_dict, global_cron_user_info_dict
from ...s3s.splatoon import Splatoon
from ...utils import get_msg_id, convert_td


async def create_refresh_token_tasks():
    """创建刷新token任务"""
    cron_msg = f"create_refresh_token_tasks start"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("refresh_token", "start")

    t = dt.utcnow()
    users = dict_get_all_global_users()

    # users = sorted(users, key=lambda x: x.id)
    list_user: list[tuple] = []  # 简要记录平台和user_id信息，等到具体任务内再获取user数据
    for user in users:
        list_user.append((user.platform, user.user_id))

    _pool = 5
    for i in range(0, len(list_user), _pool):
        _p_and_id_list = list_user[i:i + _pool]
        tasks = [refresh_token_task(p_and_id) for p_and_id in _p_and_id_list]
        res = await asyncio.gather(*tasks)
    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = f"create_refresh_token_tasks end: {str_time}\nusers_count:{len(list_user)}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("refresh_token", "end", f"耗时:{str_time}\n用户计数:{len(list_user)}")


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
        # 关闭连接池
        await splatoon.req_client.close()
    except Exception as e:
        cron_logger.warning(f"refresh_token_task error: {msg_id}, {e}")


async def clean_s3s_cache():
    """清理s3sti脚本的缓存文件夹"""
    dir_s3s_cache = f"{DIR_RESOURCE}/s3sits_git/cache"
    if os.path.exists(dir_s3s_cache):
        shutil.rmtree(dir_s3s_cache)

    cron_msg = f"clean_s3s_cache end"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("clean_s3s_cache", "end")


async def clean_global_user_info_dict():
    """清理公共用户字典"""
    await dict_clear_user_info_dict("normal")

    cron_msg = f"clean_global_user_info_dict end"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("clean_user_info_dict", "end")


async def show_dict_status():
    """显示字典当前状态"""
    cron_msg = get_dict_status()
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("status", "end")


def get_dict_status():
    """获取字典当前状态文本"""
    cron_msg = (f"global_user_cnt:{len(global_user_info_dict)}\n"
                f"cron_user_cnt:{len(global_cron_user_info_dict)}\n"
                f"global_client_cnt:{len(global_client_dict)}\n"
                f"cron_client_cnt:{len(global_cron_client_dict)}\n"
                f"ss_user:{json.dumps(global_dict_ss_user)}"
                )
    return cron_msg


async def init_nso_version():
    """将NSOAPP_VERSION 和 WEB_VIEW_VERSION 置空"""
    from ...s3s.iksm import init_global_nso_version_and_web_view_version
    init_global_nso_version_and_web_view_version()
