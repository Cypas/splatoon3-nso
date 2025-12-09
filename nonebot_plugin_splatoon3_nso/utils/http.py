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

HTTP_TIME_OUT = 60.0  # 请求超时，秒
proxy_address = plugin_config.splatoon3_proxy_address
if proxy_address:
    global_proxies = f"http://{proxy_address}"
else:
    global_proxies = None

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

    req_client = client_dict.get(msg_id)
    if req_client:
        return req_client
    else:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        req_client = ReqClient(msg_id, _type, with_proxy=with_proxy)
        client_dict.update({msg_id: req_client})
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
            proxies=global_proxies if self.with_proxy else None,
            timeout=HTTP_TIME_OUT  # 统一超时设置
        )

    async def _ensure_client_active(self) -> None:
        """确保 Client 可用，否则重建"""
        if self.client.is_closed:
            await self.client.aclose()  # 确保彻底关闭旧连接
            self._init_client()

    async def _request_with_fallback(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带自动恢复的请求核心方法"""
        try:
            await self._ensure_client_active()
            response = await self.client.request(method, url, **kwargs)
            return response
        except (httpx.TransportError, httpx.RemoteProtocolError) as e:
            # 底层连接异常时，重建 Client 并重试一次
            await self.client.aclose()
            self._init_client()
            response = await self.client.request(method, url, **kwargs)
            return response
        except RuntimeError as e:
            if "the handler is closed" in str(e):
                # 重建客户端并重试
                await self.client.aclose()
                self._init_client()
                response = await self.client.request(method, url, **kwargs)
                return response

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """自动恢复连接的 GET 请求"""
        host = urllib.parse.urlparse(url).hostname
        if not self.with_proxy and host in proxy_host_list:
            # 临时使用代理的独立请求（避免污染主 Client）
            async with httpx.AsyncClient(proxies=global_proxies) as tmp_client:
                return await tmp_client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
        return await self._request_with_fallback("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """自动恢复连接的 POST 请求"""
        host = urllib.parse.urlparse(url).hostname
        if not self.with_proxy and host in proxy_host_list:
            async with httpx.AsyncClient(proxies=global_proxies) as tmp_client:
                return await tmp_client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
        return await self._request_with_fallback("POST", url, **kwargs)

    async def close(self) -> None:
        """安全关闭 Client"""
        if not self.client.is_closed:
            await self.client.aclose()

    @staticmethod
    async def close_all(_type: str) -> None:
        """安全关闭某一类型的全部client"""
        global global_client_dict, global_cron_client_dict

        client_dict = {}
        if _type == "normal":
            client_dict = global_client_dict.copy()  # 避免遍历时修改
        elif _type == "cron":
            client_dict = global_cron_client_dict.copy()

        for req_client in list(client_dict.values()):  # 转换为list避免迭代问题
            try:
                if hasattr(req_client, "close") and callable(req_client.close):
                    await req_client.close()  # 确保await异步关闭
            except Exception as e:
                logger.warning(f"关闭全部{_type} client失败: {e}")  # 记录日志，避免中断其他关闭

        # 清空字典
        if _type == "normal":
            global_client_dict.clear()
        elif _type == "cron":
            global_cron_client_dict.clear()


global_client_dict: dict[str, ReqClient] = {}
# 登录涉及函数login in和login_2需要保持一段时间浏览器状态，在输入npf码完成登录后需要关闭client
# 普通请求也可以共用这个结构体，有利于加速网页请求，仅首次请求需要3s左右，后续只需要0.7s

global_cron_client_dict = weakref.WeakValueDictionary()

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

HTTP_TIME_OUT = 60.0  # 请求超时，秒
proxy_address = plugin_config.splatoon3_proxy_address
if proxy_address:
    global_proxies = f"http://{proxy_address}"
else:
    global_proxies = None

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

    req_client = client_dict.get(msg_id)
    if req_client:
        return req_client
    else:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        req_client = ReqClient(msg_id, _type, with_proxy=with_proxy)
        client_dict.update({msg_id: req_client})
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
            proxies=global_proxies if self.with_proxy else None,
            timeout=HTTP_TIME_OUT  # 统一超时设置
        )

    async def _ensure_client_active(self) -> None:
        """确保 Client 可用，否则重建"""
        if self.client.is_closed:
            await self.client.aclose()  # 确保彻底关闭旧连接
            self._init_client()

    async def _request_with_fallback(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带自动恢复的请求核心方法"""
        try:
            await self._ensure_client_active()
            response = await self.client.request(method, url, **kwargs)
            return response
        except (httpx.TransportError, httpx.RemoteProtocolError) as e:
            # 底层连接异常时，重建 Client 并重试一次
            await self.client.aclose()
            self._init_client()
            response = await self.client.request(method, url, **kwargs)
            return response
        except RuntimeError as e:
            if "the handler is closed" in str(e):
                # 重建客户端并重试
                await self.client.aclose()
                self._init_client()
                response = await self.client.request(method, url, **kwargs)
                return response

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """自动恢复连接的 GET 请求"""
        host = urllib.parse.urlparse(url).hostname
        if not self.with_proxy and host in proxy_host_list:
            # 临时使用代理的独立请求（避免污染主 Client）
            async with httpx.AsyncClient(proxies=global_proxies) as tmp_client:
                return await tmp_client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
        return await self._request_with_fallback("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """自动恢复连接的 POST 请求"""
        host = urllib.parse.urlparse(url).hostname
        if not self.with_proxy and host in proxy_host_list:
            async with httpx.AsyncClient(proxies=global_proxies) as tmp_client:
                return await tmp_client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
        return await self._request_with_fallback("POST", url, **kwargs)

    async def close(self) -> None:
        """安全关闭 Client"""
        if not self.client.is_closed:
            await self.client.aclose()

    @staticmethod
    async def close_all(_type: str) -> None:
        """安全关闭某一类型的全部client"""
        global global_client_dict, global_cron_client_dict

        client_dict = {}
        if _type == "normal":
            client_dict = global_client_dict.copy()  # 避免遍历时修改
        elif _type == "cron":
            client_dict = global_cron_client_dict.copy()

        for req_client in list(client_dict.values()):  # 转换为list避免迭代问题
            try:
                if hasattr(req_client, "close") and callable(req_client.close):
                    await req_client.close()  # 确保await异步关闭
            except Exception as e:
                logger.warning(f"关闭全部{_type} client失败: {e}")  # 记录日志，避免中断其他关闭

        # 清空字典
        if _type == "normal":
            global_client_dict.clear()
        elif _type == "cron":
            global_cron_client_dict.clear()


global_client_dict: dict[str, ReqClient] = {}
# 登录涉及函数login in和login_2需要保持一段时间浏览器状态，在输入npf码完成登录后需要关闭client
# 普通请求也可以共用这个结构体，有利于加速网页请求，仅首次请求需要3s左右，后续只需要0.7s

global_cron_client_dict = weakref.WeakValueDictionary()


class HttpReq(object):
    """httpx 同步请求封装（支持 HTTP/2.0）"""

    @staticmethod
    def get(url, with_proxy=False, **kwargs) -> Response:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        proxies = global_proxies if with_proxy else None

        # 使用同步 Client 并启用 HTTP/2.0
        with httpx.Client(proxies=proxies, http2=True) as client:
            response = client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
        return response

    @staticmethod
    def post(url, with_proxy=False, **kwargs) -> Response:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        proxies = global_proxies if with_proxy else None

        # 使用同步 Client 并启用 HTTP/2.0
        with httpx.Client(proxies=proxies, http2=True) as client:
            response = client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
        return response


class AsHttpReq(object):
    """httpx 异步请求封装（支持 HTTP/2.0）"""

    @staticmethod
    async def get(url, with_proxy=False, **kwargs) -> Response:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        if with_proxy:
            proxies = global_proxies
        else:
            proxies = None
        async with httpx.AsyncClient(proxies=proxies, http2=True) as client:
            response = await client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
            return response

    @staticmethod
    async def post(url, with_proxy=False, **kwargs) -> Response:
        # 配置项是否全部代理
        if not plugin_config.splatoon3_proxy_list_mode:
            with_proxy = True
        if with_proxy:
            proxies = global_proxies
        else:
            proxies = None
        async with httpx.AsyncClient(proxies=proxies, http2=True) as client:
            response = await client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
            return response

