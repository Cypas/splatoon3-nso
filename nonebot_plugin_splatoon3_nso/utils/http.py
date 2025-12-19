import gc
import time
import urllib.parse
import weakref
import httpx
import urllib.parse
from typing import Optional

import httpx
from httpx import Response
from nonebot import logger

from .utils import get_msg_id
from ..config import plugin_config

# ===================== 基础配置 =====================
HTTP_TIME_OUT = 60.0  # 请求超时，秒
proxy_address = plugin_config.splatoon3_proxy_address

global_proxies = f"http://{proxy_address}" if proxy_address else None

# 需要代理访问的地址
proxy_host_list = plugin_config.splatoon3_proxy_list


async def get_file_url(url):
    """从网页读获取图片"""
    try:
        resp = await AsHttpReq.get(url)
        resp.read()
        data = resp.content
        return data
    except Exception as e:
        logger.warning(f"http get file_data error,{e}")
        return None
    finally:
        # 确保响应体被关闭（释放连接）
        if resp:
            try:
                await resp.close()
            except:
                pass


def get_or_init_client(platform, user_id, _type="normal", with_proxy=False):
    """获取msg_id对应的ReqClient
    为每个会话创建唯一ReqClient，能极大加快请求速度，如第一次请求3s，第二次只需要0.7s
    """
    msg_id = get_msg_id(platform, user_id)
    global global_client_dict
    global global_cron_client_dict

    client_dict = {}
    if _type == "normal":
        client_dict = global_client_dict
    elif _type == "cron":
        # 定时任务
        client_dict = global_cron_client_dict

    # 获取客户端（处理不同字典结构）
    req_client = None
    if _type == "normal":
        entry = client_dict.get(msg_id)
        if entry:
            req_client, _ = entry
    else:
        req_client = client_dict.get(msg_id)

    if req_client:
        # 更新最后使用时间
        if _type == "normal":
            global_client_dict[msg_id] = (req_client, time.time())
        return req_client
    else:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        req_client = ReqClient(msg_id, _type, with_proxy=with_proxy)

        # 存储客户端（不同结构）
        if _type == "normal":
            global_client_dict[msg_id] = (req_client, time.time())
        else:
            client_dict[msg_id] = req_client

        return req_client


class ReqClient:
    """二次封装的httpx client会话管理（自动恢复连接版）"""

    def __init__(self, msg_id: str, _type=None, with_proxy: bool = False):
        self.msg_id = msg_id
        self._type = _type
        self.with_proxy = with_proxy
        # 初始化时直接创建 Client
        self._init_client()

    def _init_client(self) -> None:
        """初始化或重建 AsyncClient"""
        self.client = httpx.AsyncClient(
            proxy=global_proxies if self.with_proxy else None,
            timeout=HTTP_TIME_OUT  # 统一超时设置
        )

    async def _ensure_client_active(self) -> None:
        """确保 Client 可用，否则重建"""
        if self.client.is_closed:
            await self.client.aclose()  # 确保彻底关闭旧连接
            self._init_client()

    async def _request_with_fallback(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带自动恢复的请求核心方法（增加异常上限）"""
        retry_count = 0
        max_retry = 1  # 最多重试1次
        while retry_count <= max_retry:
            try:
                await self._ensure_client_active()
                response = await self.client.request(method, url, **kwargs)
                return response
            except (httpx.TransportError, httpx.RemoteProtocolError, RuntimeError) as e:
                retry_count += 1
                if retry_count > max_retry:
                    raise  # 超过重试次数，抛出异常
                # 重建客户端并重试
                await self.client.aclose()
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
        """安全关闭 Client"""
        if not self.client.is_closed:
            await self.client.aclose()

    @staticmethod
    async def close_all(_type: str) -> None:
        """安全关闭某一类型的全部client（修复弱引用处理）"""
        global global_client_dict, global_cron_client_dict

        # 处理普通客户端
        if _type == "normal":
            client_items = list(global_client_dict.values())
            global_client_dict.clear()
            for client, _ in client_items:
                try:
                    await client.close()
                except Exception as e:
                    logger.warning(f"关闭普通客户端失败: {e}")
        # 处理定时任务客户端（弱引用无需clear）
        elif _type == "cron":
            for msg_id in list(global_cron_client_dict.keys()):
                client = global_cron_client_dict.get(msg_id)
                if client:
                    try:
                        await client.close()
                    except Exception as e:
                        logger.warning(f"关闭定时任务客户端 {msg_id} 失败: {e}")

            gc.collect()  # 手动触发GC，立即回收


# ===================== 全局变量  =====================
# 1. 普通客户端使用带超时清理的字典
global_client_dict: dict[str, tuple[ReqClient, float]] = {}
# 登录涉及函数login in和login_2需要保持一段时间浏览器状态，在输入npf码完成登录后需要关闭client
# 普通请求也可以共用这个结构体，有利于加速网页请求，仅首次请求需要3s左右，后续只需要0.7s
# 2. 定时任务客户端保留弱引用
global_cron_client_dict = weakref.WeakValueDictionary()
# 3. 普通客户端超时时间（48h未使用则清理）
CLIENT_TIMEOUT = 60 * 60 * 48


# ===================== 简易请求封装 =====================
class HttpReq(object):
    """httpx 同步请求封装（支持 HTTP/2.0）"""

    @staticmethod
    def get(url, with_proxy=False, **kwargs) -> Response:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        proxies = global_proxies if with_proxy else None
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
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        proxies = global_proxies if with_proxy else None
        with httpx.Client(
                proxy=proxies,
                http2=True,
                timeout=HTTP_TIME_OUT,
                limits=httpx.Limits(max_connections=5)
        ) as client:
            response = client.post(url, **kwargs)
        return response


class AsHttpReq(object):
    """httpx 异步请求封装（支持 HTTP/2.0）"""

    @staticmethod
    async def get(url, with_proxy=False, **kwargs) -> Response:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        proxies = global_proxies if with_proxy else None
        async with httpx.AsyncClient(
                proxy=proxies,
                http2=True,
                timeout=HTTP_TIME_OUT,
                limits=httpx.Limits(max_connections=5)
        ) as client:
            response = await client.get(url, **kwargs)
            return response

    @staticmethod
    async def post(url, with_proxy=False, **kwargs) -> Response:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        proxies = global_proxies if with_proxy else None
        async with httpx.AsyncClient(
                proxy=proxies,
                http2=True,
                timeout=HTTP_TIME_OUT,
                limits=httpx.Limits(max_connections=5)
        ) as client:
            response = await client.post(url, **kwargs)
            return response

