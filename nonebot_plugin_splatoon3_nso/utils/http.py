import asyncio
import gc
import threading
import time
import urllib.parse
import weakref
import httpx
from typing import Optional, Dict, Any, Union

from async_lru import alru_cache
from httpx import Response, ConnectError, ConnectTimeout, ReadTimeout
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
CLIENT_TIMEOUT = 60 * 60 * 10  # 10小时未使用则清理

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
            except (httpx.TransportError, httpx.RemoteProtocolError, RuntimeError, httpx.ConnectTimeout,
                    httpx.ConnectTimeout) as e:
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
                limits=httpx.Limits(max_connections=20)
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
                limits=httpx.Limits(max_connections=20)
        ) as client:
            response = client.post(url, **kwargs)
        return response


# AsyncClient 全局配置（复用核心）
CLIENT_CONFIG: Dict[str, Any] = {
    "http2": False,
    "timeout": httpx.Timeout(connect=HTTP_TIME_OUT // 2, read=HTTP_TIME_OUT, write=HTTP_TIME_OUT // 2,
                             pool=HTTP_TIME_OUT // 3),
    "limits": httpx.Limits(max_connections=300, max_keepalive_connections=60),
}

# 代理检测配置（新增）
PROXY_CHECK_TIMEOUT = 30  # 代理检测超时时间（秒，要短）
PROXY_CHECK_CACHE_EXPIRE = 300  # 代理可用性缓存过期时间（秒，5分钟）
MAX_RETRIES = 1  # 指数退避重试次数（和原有代码一致，统一抽为全局配置）
# 类型别名（新增，简化代码）
ProxyStatus = bool  # True=代理可用，False=代理不可用


class AsHttpReq:
    """
    按「域名+代理标识」分组复用 AsyncClient
    - 同时维护带代理/不带代理的双实例
    - 根据 with_proxy + url 自动匹配对应实例
    - 新增：代理故障自动降级直连 + 缓存检测结果 + 自动恢复
    """
    # 存储分组Client：Key = "域名_代理标识"（如 "google.com_True"），Value = AsyncClient实例
    _clients: Dict[str, httpx.AsyncClient] = {}
    # 异步锁：避免并发创建Client（延迟初始化，避免事件循环绑定问题）
    _client_lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_client_lock(cls) -> asyncio.Lock:
        """获取或创建当前事件循环的锁"""
        if cls._client_lock is None:
            cls._client_lock = asyncio.Lock()
        return cls._client_lock

    @classmethod
    async def _get_client(cls, url: str, with_proxy: bool = False) -> httpx.AsyncClient:
        """
        按「域名+代理标识」获取/创建Client实例
        :param url: 请求URL（解析域名用）
        :param with_proxy: 是否使用代理（显式指定）
        :return: 复用的AsyncClient实例
        """
        # 1. 解析URL域名
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.hostname or "default"  # 无域名则用default

        # 2. 确定最终是否使用代理（结合显式参数+域名白名单）
        # 规则：with_proxy=True 或 域名在代理白名单中 → 使用代理
        use_proxy = with_proxy or (domain in proxy_host_list)

        # 3. 生成分组Key（域名 + 代理标识）
        client_key = f"{domain}_{use_proxy}"

        client_lock = cls._get_client_lock()
        async with client_lock:
            # 4. 无实例/实例已关闭 → 创建新Client
            if client_key not in cls._clients or cls._clients[client_key].is_closed:
                # 配置代理（仅use_proxy=True时生效）
                proxies = global_proxies if use_proxy else None

                # 创建分组专属Client
                cls._clients[client_key] = httpx.AsyncClient(
                    proxy=proxies,
                    **CLIENT_CONFIG
                )
                logger.info(f"创建分组Client：{client_key}（代理：{use_proxy}）")

            # 5. 返回复用的Client实例
            return cls._clients[client_key]

    # ===================== 新增：代理可用性检测 + 缓存 =====================
    @classmethod
    @alru_cache(maxsize=None)  # 无上限缓存，靠过期时间控制
    async def _check_proxy_available(cls, cache_key: str) -> ProxyStatus:
        """
        检测代理是否可用，带缓存（cache_key为随机值，用于控制过期）
        :param cache_key: 缓存键（由时间戳生成，控制过期）
        :return: True=可用，False=不可用
        """
        try:
            # 检测逻辑：请求公共可访问地址，仅验证连接/代理转发能力
            async with httpx.AsyncClient(timeout=PROXY_CHECK_TIMEOUT, proxy=global_proxies) as test_client:
                resp = await test_client.get(
                    url="https://accounts.nintendo.com/api/passkey/authentication?context=login",
                    follow_redirects=True
                )
            # 状态码2xx即认为代理可用
            is_available = resp.status_code // 100 == 2
            if not is_available:
                logger.warning(f"代理检测返回非2xx状态码：{resp.status_code}")
            return is_available
        except Exception as e:
            # 任何异常都认为代理不可用（连接失败/超时/代理拒绝等）
            logger.warning(f"代理检测失败，判定为不可用 | 原因：{type(e).__name__}: {str(e)[:50]}")
            return False

    @classmethod
    async def is_proxy_available(cls) -> ProxyStatus:
        """
        对外的代理检测方法（带自动过期缓存）
        原理：用当前时间戳//过期时间生成cache_key，相同key复用缓存，过期后自动生成新key
        """
        cache_key = str(int(asyncio.get_event_loop().time()) // PROXY_CHECK_CACHE_EXPIRE)
        return await cls._check_proxy_available(cache_key)

    # ===================== 新增：直连请求兜底（无代理）=====================
    @classmethod
    async def _request_direct(cls, method: str, url: str, **kwargs) -> Response:
        """
        直连请求兜底方法：创建临时无代理Client发起请求（不污染原有分组Client）
        :param method: 请求方法
        :param url: 请求URL
        :param kwargs: 其他httpx参数
        :return: Response
        """
        async with httpx.AsyncClient(**CLIENT_CONFIG) as temp_client:
            method_func = getattr(temp_client, method.lower())
            return await method_func(url, **kwargs)

    @classmethod
    async def _request(cls, method: str, url: str, with_proxy: bool = False, **kwargs) -> Union[Response, str, None]:
        """
        核心请求方法：原有逻辑 + 代理故障自动降级直连 + 增强异常处理
        :param method: get/post/put等
        :param url: 请求URL
        :param with_proxy: 是否显式指定使用代理
        :param kwargs: 其他请求参数（headers/json/data等）
        :return: Response | 错误标识字符串 | None
        """
        # 1. 获取匹配的Client实例（自动判断是否用代理）
        client = await cls._get_client(url, with_proxy)
        # 通过_clients的key反向解析当前client是否使用代理
        # 遍历键值对，匹配当前client实例，拆分key得到代理标识
        current_use_proxy = False
        for key, inst in cls._clients.items():
            if inst is client:  # 匹配到当前Client实例
                # 拆分key：按_分割，最后一部分是代理标识（True/False）
                proxy_flag = key.split("_")[-1]
                current_use_proxy = proxy_flag == "True"
                break

        # 2. 定义请求执行函数（支持切换为直连）
        async def _do_request(use_direct: bool = False):
            if use_direct:
                # 直连兜底：调用新增的直连方法
                return await cls._request_direct(method, url, **kwargs)
            else:
                # 原有逻辑：使用分组Client
                method_func = getattr(client, method.lower())
                return await method_func(url, **kwargs)

        # 3. 指数退避重试（原有逻辑增强）
        for attempt in range(MAX_RETRIES + 1):
            try:
                # 3.1 如果当前使用代理，先检测代理可用性
                if current_use_proxy:
                    proxy_available = await cls.is_proxy_available()
                    if not proxy_available:
                        logger.info(f"请求{url}：代理不可用，自动降级为直连（本次请求）")
                        resp = await _do_request(use_direct=True)
                    else:
                        resp = await _do_request(use_direct=False)
                else:
                    # 不使用代理，直接发起请求
                    resp = await _do_request(use_direct=False)
                return resp

            # 3.2 捕获网络类异常（原有逻辑）
            except (ConnectError, ConnectTimeout, ReadTimeout) as e:
                error_flag = {
                    ConnectError: "NetConnectError",
                    ConnectTimeout: "NetConnectTimeout",
                    ReadTimeout: "NetReadTimeout"
                }.get(type(e), "NetError")
                # 最后一次重试失败 → 返回错误标识
                if attempt == MAX_RETRIES:
                    logger.error(f"请求{url}失败（{error_flag}），已达重试上限 | 详情：{str(e)}")
                    return error_flag
                # 指数退避延迟后重试
                delay = 1 * (2 ** attempt)
                await asyncio.sleep(delay)
                logger.info(f"请求{url}失败（{error_flag}），{delay}s后第{attempt + 1}次重试 | 详情：{str(e)}")

            # 3.3 捕获httpx其他异常（增强：区分代理故障和业务异常）
            except httpx.ProxyError as e:
                # 专属代理异常：直接判定代理故障，降级直连并重试（跳过指数退避）
                logger.warning(f"请求{url}触发代理专属异常，立即降级直连重试 | 详情：{type(e).__name__}: {str(e)[:50]}")
                if attempt == MAX_RETRIES:
                    logger.error(f"请求{url}代理异常，重试上限，返回错误标识")
                    return "ProxyError"
                try:
                    # 立即直连重试，不延迟
                    resp = await _do_request(use_direct=True)
                    return resp
                except Exception as retry_e:
                    logger.warning(f"直连重试仍失败 | 详情：{type(retry_e).__name__}: {str(retry_e)[:50]}")
                    continue

            # 3.4 捕获非预期异常（原有逻辑，抛出不吞掉）
            except Exception as e:
                logger.error(f"请求{url}发生非预期异常", exc_info=True)
                raise e

    # ========== 对外暴露的请求方法 ==========
    @classmethod
    async def get(cls, url: str, with_proxy: bool = False, **kwargs) -> Union[Response, str, None]:
        return await cls._request("get", url, with_proxy, **kwargs)

    @classmethod
    async def post(cls, url: str, with_proxy: bool = False, **kwargs) -> Union[Response, str, None]:
        return await cls._request("post", url, with_proxy, **kwargs)

    @classmethod
    async def put(cls, url: str, with_proxy: bool = False, **kwargs) -> Union[Response, str, None]:
        return await cls._request("put", url, with_proxy, **kwargs)

    @classmethod
    async def delete(cls, url: str, with_proxy: bool = False, **kwargs) -> Union[Response, str, None]:
        return await cls._request("delete", url, with_proxy, **kwargs)

    # ========== 新增：优雅关闭（原有_close_all_clients增强）==========
    @classmethod
    async def close_all_clients(cls) -> None:
        """关闭所有分组Client + 清空缓存 + 重置锁（应用退出时调用）"""
        client_lock = cls._get_client_lock()
        async with client_lock:
            for client_key, client in cls._clients.items():
                if not client.is_closed:
                    await client.aclose()
                    logger.info(f"关闭分组Client：{client_key}")
            cls._clients.clear()
            # 清空代理检测缓存
            cls._check_proxy_available.cache_clear()
            # 重置锁（可选，避免重启时锁绑定旧事件循环）
            cls._client_lock = None
        logger.info("所有AsHttpReq客户端已关闭，缓存已清空")
