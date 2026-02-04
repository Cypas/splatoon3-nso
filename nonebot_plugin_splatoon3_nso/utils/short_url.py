import traceback
from typing import Dict
from urllib.parse import urljoin

from nonebot import logger

from .. import plugin_config, AsHttpReq


class ZUrlClient:
    def __init__(self, host="", token=""):
        self.host = host
        self.token = token


class ZUrl:
    """
    zurl 短链生成
    """

    def __init__(self):
        """初始化zurl 短链
        从配置中读取zurl相关配置
        """
        self.config = plugin_config.splatoon3_zurl_config
        self.client = None
        if self.config.enabled:
            self._init_client()

    def _init_client(self):
        """初始化COS客户端

        使用配置中的SecretId、SecretKey和Region初始化腾讯云COS客户端
        """
        try:
            self.client = ZUrlClient(host=self.config.host, token=self.config.token)
            logger.info(f"[zurl]zurl配置初始化完成")
        except:
            pass

    def get_client(self):
        return self.client

    async def create_short_url(self, long_url, short_code=""):
        url = self.client.host
        headers = {
            "Authorization": self.client.token,
            "Content-Type": "application/json"
        }
        body = {
            "long_url": long_url,
            "short_url": short_code
        }
        try:
            resp = await AsHttpReq.post(url, headers=headers, json=body)
            res = resp.json()
            if res.get("code") == 200:
                new_short_code = res.get("data").get("short_url")
                ok = True
                short_url = self._join_url(url, new_short_code)
                return ok, short_url
            else:
                return False, f"创建失败，响应码:{res.get('code')}"
        except Exception as e:
            logger.warning(f"zurl短链请求失败:traceback:{traceback.format_exc()}")
            return False, ""

    def _join_url(host: str, suffix: str = "") -> str:
        """
        拼接URL，自动处理host末尾是否有/的问题（URL标准写法）
        :param host: 基础主机地址（如https://test.com / https://test.com/）
        :param suffix: 要拼接的后缀（默认/1234，需以/开头表示根路径）
        :return: 拼接后的完整URL
        """
        return urljoin(host, suffix)


zurl = ZUrl()
