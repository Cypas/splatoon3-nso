import cfscrape
import httpx
from httpx import Response

from ..config import plugin_config

proxy_address = plugin_config.splatoon3_proxy_address

global_client_dict: dict[httpx.Client] = {}  # 登录涉及函数login in和login_2需要保持一段时间浏览器状态，在输入npf码完成登录后需要关闭client


def cf_http_get(url: str):
    """cf get"""
    # 实例化一个create_scraper对象
    scraper = cfscrape.create_scraper()
    # 请求报错，可以加上时延
    # scraper = cfscrape.create_scraper(delay = 6)
    if proxy_address:
        proxies = {
            "http": "http://{}".format(proxy_address),
            "https": "http://{}".format(proxy_address),
        }
        # 获取网页内容 代理访问
        res = scraper.get(url, proxies=proxies)
    else:
        # 获取网页内容
        res = scraper.get(url)
    return res


async def async_http_get(url: str) -> Response:
    """async http_get"""
    response = ClientReq.get(url, timeout=5.0)
    return response


def http_get(url: str) -> Response:
    """http_get"""
    global proxy_address
    if proxy_address:
        proxies = "http://{}".format(proxy_address)
        response = httpx.get(url, proxies=proxies, timeout=5.0)
    else:
        response = httpx.get(url, timeout=5.0)
    return response


async def get_file_url(url):
    """从网页读获取图片"""
    resp = await async_http_get(url)
    resp.read()
    data = resp.content
    return data


def get_or_init_login_client(msg_id):
    """为每个登录会话创建唯一client，防止公共变量覆盖"""
    global global_client_dict
    client: httpx.Client = global_client_dict.get(msg_id)
    if client:
        return client
    else:
        client = httpx.Client()
        global_client_dict.update({msg_id: client})
        return client


def close_login_client(msg_id):
    """关闭login client"""
    global global_client_dict
    client: httpx.Client = global_client_dict.get(msg_id)
    if client:
        client.close()
        global_client_dict.pop(msg_id)


def close_all_login_client():
    """关闭全部login client"""
    global global_client_dict
    for client in global_client_dict.values():
        client.close()
    global_client_dict.clear()


class ClientReq(object):
    """httpx 请求封装为异步client请求"""

    @staticmethod
    def get(url, **kwargs):
        if proxy_address:
            proxies = "http://{}".format(proxy_address)
            async with httpx.AsyncClient(proxies=proxies) as client:
                response = await client.get(url, **kwargs)
                return response
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, **kwargs)
                return response

    @staticmethod
    def post(url, **kwargs):
        if proxy_address:
            proxies = "http://{}".format(proxy_address)
            async with httpx.AsyncClient(proxies=proxies) as client:
                response = await client.post(url, **kwargs)
                return response
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, **kwargs)
                return response