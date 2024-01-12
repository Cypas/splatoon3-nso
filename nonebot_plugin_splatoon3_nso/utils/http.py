import httpx
from httpx import Response

from ..config import plugin_config

HTTP_TIME_OUT = 5.0  # 请求超时，秒
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


def get_or_init_login_client(msg_id):
    """获取msg_id对应的LoginClient
    为每个登录会话创建唯一client，防止公共变量覆盖
    """
    global global_login_client_dict
    login_client = global_login_client_dict.get(msg_id)
    if login_client:
        return login_client
    else:
        login_client = LoginClient(msg_id)
        global_login_client_dict.update({msg_id: login_client})
        return login_client


class LoginClient:
    """登录会话管理"""
    def __init__(self, msg_id):
        self.msg_id = msg_id
        self.client = httpx.Client(proxies=proxies)

    def close(self, msg_id):
        """关闭login client"""
        self.client.close()

    async def get(self, url, **kwargs):
        """client get"""
        response = self.client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
        return response

    async def post(self, url, **kwargs):
        """client post"""
        response = self.client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
        return response

    @staticmethod
    def close_all():
        """关闭全部login client"""
        global global_login_client_dict
        for l_client in global_login_client_dict.values():
            l_client.client.close()
        global_login_client_dict.clear()


global_login_client_dict: dict[str, LoginClient] = {}  # 登录涉及函数login in和login_2需要保持一段时间浏览器状态，在输入npf码完成登录后需要关闭client


class HttpReq(object):
    """httpx 请求封装"""

    @staticmethod
    def get(url, **kwargs):
        response = httpx.get(url, proxies=proxies, timeout=HTTP_TIME_OUT, **kwargs)
        return response

    @staticmethod
    def post(url, **kwargs):
        response = httpx.post(url, proxies=proxies, timeout=HTTP_TIME_OUT, **kwargs)
        return response


class AsHttpReq(object):
    """httpx 异步请求封装"""

    @staticmethod
    async def get(url, **kwargs):
        async with httpx.AsyncClient(proxies=proxies) as client:
            response = await client.get(url, timeout=HTTP_TIME_OUT, **kwargs)
            return response

    @staticmethod
    async def post(url, **kwargs):
        async with httpx.AsyncClient(proxies=proxies) as client:
            response = await client.post(url, timeout=HTTP_TIME_OUT, **kwargs)
            return response

