import asyncio
import gc
import threading
import time
import urllib.parse
import weakref
import httpx
from typing import Optional, Dict
from httpx import Response, ConnectError, ConnectTimeout
from nonebot import logger

from .utils import get_msg_id
from ..config import plugin_config

# ===================== 基础配置 =====================
HTTP_TIME_OUT = 60.0  # 请求超时，秒
proxy_address = plugin_config.splatoon3_proxy_address

global_proxies = f"http://{proxy_address}" if proxy_address else None

# 局部代理模式
proxy_list_mode = plugin_config.splatoon3_proxy_list_mode
# 需要代理访问的地址
proxy_host_list = plugin_config.splatoon3_proxy_list

# 客户端清理配置
CLIENT_TIMEOUT = 60 * 60 * 48  # 48小时未使用则清理

# ===================== 全局变量  =====================
# 1. 普通客户端：msg_id -> (ReqClient, 最后使用时间)
global_client_dict: dict[str, tuple["ReqClient", float]] = {}
# 2. 定时任务客户端：弱引用字典
global_cron_client_dict = weakref.WeakValueDictionary()


# ===================== 定时清理机制 =====================
# def start_client_cleanup_task():
#     """启动客户端定时清理任务（确保单例）"""
#     if hasattr(start_client_cleanup_task, "_started"):
#         return
#     start_client_cleanup_task._started = True
#
#     def cleanup_expired_clients():
#         """清理超时未使用的客户端"""
#         current_time = time.time()
#         expired_msg_ids = []
#
#         # 1. 筛选超时的普通客户端
#         for msg_id, (client, last_used) in global_client_dict.items():
#             if current_time - last_used > CLIENT_TIMEOUT:
#                 expired_msg_ids.append(msg_id)
#
#         # 2. 关闭并移除超时客户端
#         closed_count = 0
#         for msg_id in expired_msg_ids:
#             try:
#                 # 从字典中移除（解除强引用）
#                 client, _ = global_client_dict.pop(msg_id)
#                 # 异步关闭需要放入事件循环执行
#                 import asyncio
#                 if asyncio.get_event_loop().is_running():
#                     asyncio.create_task(client.close())
#                 closed_count += 1
#                 logger.info(f"清理超时客户端 {msg_id}（48小时未使用）")
#             except Exception as e:
#                 logger.warning(f"清理客户端 {msg_id} 失败: {e}")
#
#         # 3. 强制触发GC回收无引用对象
#         collected = gc.collect()
#         logger.debug(f"定时清理完成：关闭{closed_count}个超时客户端，GC回收{collected}个对象")
#
#         # 4. 循环执行定时任务
#         Timer(CLEANUP_INTERVAL, cleanup_expired_clients).start()
#
#     # 立即执行一次，之后定时循环
#     cleanup_expired_clients()
#
#
# # 启动定时清理
# start_client_cleanup_task()


# ===================== 核心客户端类 =====================
class ReqClient:
    """二次封装的httpx client会话管理（自动恢复连接+可彻底释放）"""

    def __init__(self, msg_id: str, _type=None, with_proxy: bool = False):
        self.msg_id = msg_id
        self._type = _type
        self.with_proxy = with_proxy
        self._closed = False  # 标记客户端是否已关闭
        self._init_client()

    def _init_client(self) -> None:
        """初始化或重建 AsyncClient"""
        if self._closed:
            raise RuntimeError(f"客户端 {self.msg_id} 已关闭，无法重新初始化")

        self.client = httpx.AsyncClient(
            proxy=global_proxies if self.with_proxy else None,
            timeout=HTTP_TIME_OUT
        )

    async def _ensure_client_active(self) -> None:
        """确保 Client 可用，否则重建（修复逻辑错误）"""
        if self._closed:
            raise RuntimeError(f"客户端 {self.msg_id} 已关闭，无法使用")

        # 正确逻辑：先检查是否关闭，未关闭才需要处理
        if self.client.is_closed:
            self._init_client()  # 直接重建，无需重复关闭

    async def _request_with_fallback(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带自动恢复的请求核心方法"""
        retry_count = 0
        max_retry = 1
        while retry_count <= max_retry:
            try:
                await self._ensure_client_active()
                response = await self.client.request(method, url, **kwargs)
                return response
            except (httpx.TransportError, httpx.RemoteProtocolError, RuntimeError, httpx.ConnectTimeout, httpx.ConnectTimeout) as e:
                retry_count += 1
                if retry_count > max_retry:
                    raise
                # 重建客户端并重试
                await self.close()  # 关闭旧连接
                self._init_client()
                logger.warning(f"请求 {url} 失败，重试({retry_count}/{max_retry}): {e}")
        raise httpx.TransportError(f"请求 {url} 重试{max_retry}次后仍失败")

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """自动恢复连接的 GET 请求"""
        host = urllib.parse.urlparse(url).hostname
        if not self.with_proxy and host in proxy_host_list:
            # 临时使用代理的独立请求（避免污染主 Client）
            async with httpx.AsyncClient(proxy=global_proxies) as tmp_client:
                return await tmp_client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
        return await self._request_with_fallback("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """自动恢复连接的 POST 请求"""
        host = urllib.parse.urlparse(url).hostname
        if not self.with_proxy and host in proxy_host_list:
            async with httpx.AsyncClient(proxy=global_proxies) as tmp_client:
                return await tmp_client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
        return await self._request_with_fallback("POST", url, **kwargs)

    async def close(self) -> None:
        """安全关闭 Client（幂等操作，避免重复关闭）"""
        if self._closed:
            return

        try:
            if not self.client.is_closed:
                await self.client.aclose()
            self._closed = True
            logger.debug(f"客户端 {self.msg_id} 已安全关闭")
        except Exception as e:
            logger.warning(f"关闭客户端 {self.msg_id} 失败: {e}")

    @staticmethod
    async def close_and_remove(platform: str, user_id: str, _type: str = "normal"):
        """关闭客户端并从全局字典中移除（彻底释放引用）"""
        msg_id = get_msg_id(platform, user_id)
        client_dict = global_client_dict if _type == "normal" else global_cron_client_dict

        # 1. 从字典中移除（解除强引用）
        req_client = None
        if _type == "normal":
            entry = client_dict.pop(msg_id, None)
            req_client = entry[0] if entry else None
        else:
            req_client = client_dict.pop(msg_id, None)

        # 2. 关闭连接
        if req_client and not req_client._closed:
            try:
                await req_client.close()
            except Exception as e:
                logger.warning(f"关闭客户端 {msg_id} 失败: {e}")

        # 3. 强制解除引用并触发GC
        del req_client
        gc.collect()
        logger.info(f"客户端 {msg_id} 已从全局字典移除并释放引用")

    @staticmethod
    async def close_all(_type: str) -> None:
        """安全关闭某一类型的全部client（彻底释放引用）"""
        global global_client_dict, global_cron_client_dict

        try:
            if _type == "normal":
                # 处理普通客户端：先清空字典，再关闭连接
                client_items = list(global_client_dict.values())
                global_client_dict.clear()  # 立即解除所有强引用

                closed_count, failed_count = 0, 0
                for client, _ in client_items:
                    try:
                        if not client._closed:
                            await client.close()
                        closed_count += 1
                    except Exception as e:
                        logger.warning(f"关闭普通客户端失败: {e}")
                        failed_count += 1

                # 解除列表引用
                del client_items
                logger.info(f"普通客户端批量关闭完成：成功{closed_count}个，失败{failed_count}个")

            elif _type == "cron":
                # 处理定时任务客户端：遍历弱引用字典
                msg_ids = list(global_cron_client_dict.keys())
                closed_count, failed_count = 0, 0

                for msg_id in msg_ids:
                    client = global_cron_client_dict.pop(msg_id, None)
                    if client and not client._closed:
                        try:
                            await client.close()
                            closed_count += 1
                        except Exception as e:
                            logger.warning(f"关闭定时任务客户端 {msg_id} 失败: {e}")
                            failed_count += 1

                logger.info(f"定时任务客户端批量关闭完成：成功{closed_count}个，失败{failed_count}个")

            # 全局GC回收
            collected = gc.collect()
            logger.info(f"批量关闭后触发GC，回收{collected}个对象")

        except Exception as e:
            logger.error(f"批量关闭{_type}类型客户端异常: {e}", exc_info=True)
            raise


# ===================== 客户端获取方法 =====================
def get_or_init_client(platform, user_id, _type="normal", with_proxy=False):
    """获取msg_id对应的ReqClient（确保引用更新）"""
    msg_id = get_msg_id(platform, user_id)
    global global_client_dict, global_cron_client_dict

    client_dict = global_client_dict if _type == "normal" else global_cron_client_dict

    # 获取现有客户端
    req_client = None
    if _type == "normal":
        entry = client_dict.get(msg_id)
        if entry:
            req_client, _ = entry
    else:
        req_client = client_dict.get(msg_id)

    # 客户端存在且未关闭，更新最后使用时间
    if req_client and not req_client._closed:
        # 更新最后使用时间
        if _type == "normal":
            global_client_dict[msg_id] = (req_client, time.time())
        return req_client

    # 新建客户端
    if not proxy_list_mode:
        with_proxy = True
    req_client = ReqClient(msg_id, _type, with_proxy=with_proxy)

    # 存储客户端
    if _type == "normal":
        global_client_dict[msg_id] = (req_client, time.time())
    else:
        client_dict[msg_id] = req_client

    return req_client


# ===================== 工具方法 =====================
async def get_file_url(url):
    """从网页获取图片（修复资源泄漏）"""
    resp = None  # 初始化resp，避免异常分支未定义
    try:
        resp = await AsHttpReq.get(url)
        data = resp.content  # resp.read() 无需手动调用，content会自动读取
        return data
    except Exception as e:
        logger.warning(f"http get file_data error: {e}")
        return None
    finally:
        # 关闭响应（异步响应使用aclose）
        if resp:
            try:
                await resp.aclose()
            except Exception as e:
                logger.warning(f"关闭响应失败: {e}")


# ===================== 简易请求封装 =====================
class HttpReq(object):
    """httpx 同步请求封装（支持 HTTP/2.0）"""

    @staticmethod
    def get(url, with_proxy=False, **kwargs) -> Response:
        """同步GET请求，支持基于域名的代理过滤"""
        # 配置项是否全部代理
        if not proxy_list_mode:
            with_proxy = True

        proxies = None
        # 解析URL的域名并判断是否需要代理
        host = urllib.parse.urlparse(url).hostname
        if not with_proxy and host in proxy_host_list:
            proxies = global_proxies

        with httpx.Client(
                proxy=proxies,
                http2=True,
                timeout=HTTP_TIME_OUT,
                limits=httpx.Limits(max_connections=5)
        ) as client:
            response = client.get(url, **kwargs)
        return response

    @staticmethod
    def post(url, with_proxy=False, **kwargs) -> Response:
        """同步POST请求，支持基于域名的代理过滤"""
        # 配置项是否全部代理
        if not proxy_list_mode:
            with_proxy = True

        proxies = None
        # 解析URL的域名并判断是否需要代理（新增host过滤逻辑）
        host = urllib.parse.urlparse(url).hostname
        if not with_proxy and host in proxy_host_list:
            proxies = global_proxies

        with httpx.Client(
                proxy=proxies,
                http2=True,
                timeout=HTTP_TIME_OUT,
                limits=httpx.Limits(max_connections=5)
        ) as client:
            response = client.post(url, **kwargs)
        return response


class AsHttpReq(object):
    """httpx 异步请求封装（信号量版：修复cls不存在错误）"""

    # 1. 线程隔离存储（每个线程独立的信号量和Client池）
    _thread_local = threading.local()
    # 2. 全局关闭标记（同步锁保护）
    _global_closed = False
    _global_lock = threading.Lock()
    # 3. 全局跨线程信号量（限制总请求并发数）
    _global_semaphore = threading.Semaphore(20)  # 最多20个线程同时请求

    @classmethod
    def _get_thread_semaphore(cls) -> asyncio.Semaphore:
        """获取当前线程的异步信号量（控制协程并发）"""
        if not hasattr(cls._thread_local, "semaphore"):
            # 每个线程最多同时创建10个Client（可根据服务器配置调整）
            cls._thread_local.semaphore = asyncio.Semaphore(10)
        return cls._thread_local.semaphore

    @classmethod
    def _get_thread_client_pool(cls) -> Dict[str, httpx.AsyncClient]:
        """获取当前线程的Client池"""
        if not hasattr(cls._thread_local, "client_pool"):
            cls._thread_local.client_pool = {}
        return cls._thread_local.client_pool

    @classmethod
    def _create_client(cls, with_proxy: bool, host: str) -> httpx.AsyncClient:
        """创建Client实例"""
        proxies = None
        if not with_proxy and host in proxy_host_list:
            proxies = global_proxies

        return httpx.AsyncClient(
            proxy=proxies,
            http2=True,
            timeout=HTTP_TIME_OUT,
            limits=httpx.Limits(
                max_connections=15,
                max_keepalive_connections=10,
                keepalive_expiry=30.0
            ),
            follow_redirects=True,
        )

    @staticmethod
    async def _request(method: str, url: str, with_proxy: bool = False, **kwargs) -> Optional[Response]:
        """核心请求方法（信号量版：修复cls不存在错误）"""
        # 1. 全局关闭检查（同步信号量保护）
        with AsHttpReq._global_semaphore:
            with AsHttpReq._global_lock:
                if AsHttpReq._global_closed:
                    raise RuntimeError("全局已关闭，无法发起请求")

            host = urllib.parse.urlparse(url).hostname
            client = None
            is_temp_client = False
            thread_sem = AsHttpReq._get_thread_semaphore()
            client_pool = AsHttpReq._get_thread_client_pool()
            proxy_key = f"proxy_{with_proxy}_{host}" if host else f"proxy_{with_proxy}"

            # 初始化信号量获取状态
            acquired = False

            try:
                # 2. 异步信号量控制（最多10个协程同时创建Client）
                # 设置超时：避免循环关闭时一直等待
                acquired = await asyncio.wait_for(thread_sem.acquire(), timeout=5.0)
                if not acquired:
                    raise RuntimeError("获取异步信号量超时")

                # 3. 获取/创建Client
                if proxy_key in client_pool and not client_pool[proxy_key].is_closed:
                    client = client_pool[proxy_key]
                else:
                    # 创建新Client（信号量已限制并发数）
                    client = AsHttpReq._create_client(with_proxy, host)
                    client_pool[proxy_key] = client

                # 4. 执行POST/GET请求（重试逻辑）
                max_retries = 1
                for attempt in range(max_retries + 1):
                    try:
                        if method.lower() == "post":
                            response = await client.post(url,** kwargs)
                        elif method.lower() == "get":
                            response = await client.get(url, **kwargs)
                        else:
                            raise ValueError(f"不支持的请求方法: {method}")

                        await response.aread()
                        return response

                    except (ConnectError, ConnectTimeout) as e:
                        if attempt == max_retries:
                            raise e
                        # 重试前重置Client（避免无效连接）
                        if client:
                            await AsHttpReq._safe_close_client(client)
                            del client_pool[proxy_key]
                        client = AsHttpReq._create_client(with_proxy, host)
                        client_pool[proxy_key] = client
                        print(f"[{threading.current_thread().name}] 请求 {url} 重试: {e}")

            except asyncio.TimeoutError:
                # 信号量等待超时 → 创建临时Client兜底
                client = AsHttpReq._create_temp_client(with_proxy, host)
                is_temp_client = True
                if method.lower() == "post":
                    response = await client.post(url, **kwargs)
                else:
                    response = await client.get(url, **kwargs)
                await response.aread()
                return response
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    print(f"[{threading.current_thread().name}] 请求 {url} 失败: 事件循环已关闭")
                    return None
                raise
            finally:
                # 5. 释放信号量 + 清理临时Client
                if acquired:
                    thread_sem.release()
                if client and is_temp_client:
                    await AsHttpReq._safe_close_client(client)

    # ========== 辅助方法 ==========
    @classmethod
    def _create_temp_client(cls, with_proxy: bool, host: str) -> httpx.AsyncClient:
        """创建临时Client（信号量超时兜底）"""
        proxies = None
        if not with_proxy and host in proxy_host_list:
            proxies = global_proxies
        return httpx.AsyncClient(
            proxy=proxies,
            http2=True,
            timeout=HTTP_TIME_OUT,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=5)
        )

    @staticmethod
    async def _safe_close_client(client: httpx.AsyncClient):
        """安全关闭Client"""
        if client.is_closed:
            return
        await client.aclose()


    # ========== 对外接口 ==========
    @staticmethod
    async def post(url: str, with_proxy: bool = False, **kwargs) -> Response:
        """异步POST请求（信号量版，核心修复）"""
        response = await AsHttpReq._request("post", url, with_proxy, **kwargs)
        return response

    @staticmethod
    async def get(url: str, with_proxy: bool = False, **kwargs) -> Response:
        """异步GET请求（信号量版）"""
        response = await AsHttpReq._request("get", url, with_proxy, **kwargs)
        return response

    # ========== 清理方法 ==========
    @classmethod
    async def close_current_thread_clients(cls):
        """关闭当前线程的Client池"""
        client_pool = cls._get_thread_client_pool()
        for client in client_pool.values():
            await cls._safe_close_client(client)
        client_pool.clear()
        gc.collect()

    @classmethod
    def close_all_clients(cls):
        """全局关闭（同步方法，无循环依赖）"""
        with cls._global_lock:
            cls._global_closed = True
        # 清理所有线程的Client池（简化版：直接清空）
        cls._thread_local.__dict__.clear()
        gc.collect()