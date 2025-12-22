import asyncio
import gc
import json
import os
import shutil
import sys
import time

from nonebot import logger
from pympler import muppy, asizeof, summary

from .utils import cron_logger
from datetime import datetime as dt

from ..send_msg import cron_notify_to_channel
from ...s3s.iksm import GlobalRateLimiter, init_global_nso_version_and_web_view_version
from ...s3s.splatnet_image import global_dict_ss_user, cleanup_browser
from ...utils.utils import DIR_RESOURCE
from ...utils.http import global_client_dict, global_cron_client_dict, CLIENT_TIMEOUT
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

    counters = {
        "success_cnt": 0,
    }
    _pool = 2
    semaphore = asyncio.Semaphore(_pool)  # 并发控制

    async def process_user(p_and_id):
        async with semaphore:  # 限制并发数
            return await refresh_token_task(p_and_id)  # 直接返回任务结果

    # 动态提交所有任务（无需手动分批）
    tasks = [process_user(p_and_id) for p_and_id in list_user]

    for coro in asyncio.as_completed(tasks):
        r = await coro  # 获取任务结果
        if r:
            counters["success_cnt"] += 1

    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = f"create_refresh_token_tasks end: {str_time}\nusers_count:{len(list_user)},success_cnt:{counters['success_cnt']}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("refresh_token", "end",
                                 f"耗时:{str_time}\n用户计数:{len(list_user)},成功:{counters['success_cnt']}")


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
        success = await splatoon.refresh_gtoken_and_bullettoken()
        return success
    except Exception as e:
        cron_logger.warning(f"refresh_token_task error: {msg_id}, {e}")
        return False


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
    await dict_clear_user_info_dict("cron")
    gc.collect()

    cron_msg = f"clean_global_user_info_dict end"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("clean_user_info_dict", "end")


async def show_dict_status():
    """显示字典当前状态"""
    cron_msg = await get_dict_status()
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("status", "end", cron_msg)


async def get_dict_status():
    """获取字典当前状态文本"""
    # limiter = await GlobalRateLimiter.get_instance(rate=2)

    # 获取状态
    # limiter_dict = await limiter.get_serializable_state()

    # Python内部的内存
    gc_stats = gc.get_stats()
    gen0 = gc_stats[0]['collections']
    gen1 = gc_stats[1]['collections']
    gen2 = gc_stats[2]['collections']

    cron_msg = (f"global_user_cnt:{len(global_user_info_dict)}\n"
                f"cron_user_cnt:{len(global_cron_user_info_dict)}\n"
                f"global_client_cnt:{len(global_client_dict)}\n"
                f"cron_client_cnt:{len(global_cron_client_dict)}\n"
                f"Python GC统计 - 0代:{gen0}次, 1代:{gen1}次, 2代:{gen2}次"
                # f"limiter:{json.dumps(limiter_dict)}\n"
                # f"ss_user:{json.dumps(global_dict_ss_user)}"
                )
    get_python_internal_memory()
    return cron_msg


def get_python_internal_memory():
    """获取Python内部的内存占用（兼容Pydantic 2.x版本）"""
    # 第一步：执行深度GC，清理垃圾对象
    gc.collect(2)

    # 第二步：获取Python内部所有存活对象，并过滤掉Pydantic的Mock对象
    all_live_objects = []
    for obj in gc.get_objects():
        # 过滤掉会触发Pydantic错误的对象类型
        try:
            # 跳过Pydantic的MockValSer对象
            if str(type(obj)).find("MockValSer") != -1:
                continue
            # 跳过Pydantic的内部mock相关对象
            if hasattr(obj, '_error_message') and hasattr(obj, '_code'):
                continue
            all_live_objects.append(obj)
        except:
            # 跳过任何无法访问的对象
            continue

    # 第三步：统计总内存（递归计算所有引用对象）
    try:
        total_memory_bytes = asizeof.asizeof(all_live_objects)
        total_memory_mb = total_memory_bytes / 1024 / 1024
    except Exception as e:
        # 降级方案：使用sys模块统计基础内存
        total_memory_mb = 0.0
        for obj in all_live_objects[:10000]:  # 限制数量避免超时
            try:
                total_memory_mb += sys.getsizeof(obj) / 1024 / 1024
            except:
                continue
        print(f"asizeof统计失败，使用降级方案: {e}")

    # 第四步：按类型统计内存分布（跳过Pydantic相关类型）
    try:
        sum1 = summary.summarize(all_live_objects)
        # 过滤Pydantic相关的统计项
        filtered_sum = []
        for item in sum1:
            type_name = str(item[0])
            if "pydantic" not in type_name and "MockValSer" not in type_name:
                filtered_sum.append(item)

        print("=== Python内部内存分布（按对象类型） ===")
        summary.print_(filtered_sum, limit=10)  # 显示前10个内存占用最多的对象类型
    except Exception as e:
        print(f"内存分布统计失败: {e}")

    return total_memory_mb

async def init_nso_version():
    """将NSOAPP_VERSION 和 WEB_VIEW_VERSION 置空"""
    init_global_nso_version_and_web_view_version()


async def clean_expired_clients():
    """定时清理过期的客户端（后台任务）"""
    try:
        current_time = time.time()
        expired_keys = []

        # 清理普通客户端字典
        for msg_id, (client, create_time) in global_client_dict.items():
            if current_time - create_time > CLIENT_TIMEOUT:
                expired_keys.append(msg_id)

        # 关闭并移除过期客户端
        for msg_id in expired_keys:
            client, _ = global_client_dict.pop(msg_id)
            try:
                await client.close()
                logger.debug(f"清理过期客户端: {msg_id}")
            except Exception as e:
                logger.warning(f"清理客户端 {msg_id} 失败: {e}")

    except Exception as e:
        logger.error(f"定时清理客户端出错: {e}")
