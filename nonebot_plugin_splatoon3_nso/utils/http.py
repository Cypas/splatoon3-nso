import httpx
from httpx import Response

from . import get_msg_id
from ..config import plugin_config

HTTP_TIME_OUT = 10.0  # 请求超时，秒
proxy_address = plugin_config.splatoon3_proxy_address
if proxy_address:
    proxies = "http://{}".format(proxy_address)
else:
    proxies = None


async def get_file_url(url):
    """从网页读获取图片"""
    resp = await AsHttpReq.get(url)
    resp.read()
    data = resp.content
    return data


def get_or_init_client(platform, user_id, _type="normal"):
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
        req_client = ReqClient(msg_id, _type)
        client_dict.update({msg_id: req_client})
        return req_client


class ReqClient:
    """二次封装的httpx client会话管理"""

    def __init__(self, msg_id, _type=None):
        self.msg_id = msg_id
        self.client = httpx.AsyncClient(proxies=proxies)
        self._type = _type  # 标记client的作用

    async def close(self):
        """关闭client"""
        await self.client.aclose()

    async def get(self, url, **kwargs) -> Response:
        """client get"""
        if self.client.is_closed:
            self.client = httpx.AsyncClient(proxies=proxies)
        response = await self.client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
        return response

    async def post(self, url, **kwargs) -> Response:
        """client post"""
        if self.client.is_closed:
            self.client = httpx.AsyncClient(proxies=proxies)
        response = await self.client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
        return response

    @staticmethod
    async def close_all(_type: str):
        """关闭某一类型的全部client"""
        global global_client_dict
        global global_cron_client_dict

        client_dict = {}
        if _type == "normal":
            client_dict = global_client_dict
        elif _type == "cron":
            # 定时任务
            client_dict = global_cron_client_dict

        for req_client in client_dict.values():
            await req_client.client.aclose()
        client_dict.clear()


global_client_dict: dict[str, ReqClient] = {}
# 登录涉及函数login in和login_2需要保持一段时间浏览器状态，在输入npf码完成登录后需要关闭client
# 普通请求也可以共用这个结构体，有利于加速网页请求，仅首次请求需要3s左右，后续只需要0.7s

global_cron_client_dict: dict[str, ReqClient] = {}


class HttpReq(object):
    """httpx 请求封装"""

    @staticmethod
    def get(url, **kwargs) -> Response:
        response = httpx.get(url, proxies=proxies, timeout=HTTP_TIME_OUT, **kwargs)
        return response

    @staticmethod
    def post(url, **kwargs) -> Response:
        response = httpx.post(url, proxies=proxies, timeout=HTTP_TIME_OUT, **kwargs)
        return response


class AsHttpReq(object):
    """httpx 异步请求封装"""

    @staticmethod
    async def get(url, **kwargs) -> Response:
        async with httpx.AsyncClient(proxies=proxies) as client:
            response = await client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
            return response

    @staticmethod
    async def post(url, **kwargs) -> Response:
        async with httpx.AsyncClient(proxies=proxies) as client:
            response = await client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
            return response
