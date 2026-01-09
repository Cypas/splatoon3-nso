# (ↄ) 2017-2022 eli fessler (frozenpandaman), clovervidia
# https://github.com/frozenpandaman/s3s
# License: GPLv3
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
import threading
import urllib
import random
import asyncio
from typing import Dict, Any, Optional, Union

import httpx
import jwt
from bs4 import BeautifulSoup
from jwt import ExpiredSignatureError, DecodeError, InvalidTokenError
from nonebot import logger as nb_logger
from weakref import WeakKeyDictionary

from .utils import SPLATNET3_URL
from ..utils import BOT_VERSION, AsHttpReq

S3S_AGENT = "s3s - github.com/Cypas/splatoon3-nso"  # s3s agent
S3S_VERSION = "0.7.0"  # s3s脚本版本号
NSOAPP_VERSION = "unknown"
NSOAPP_VER_FALLBACK = "3.2.0"  # fallback
WEB_VIEW_VERSION = "unknown"
WEB_VIEW_VER_FALLBACK = "10.0.0-cba84fcd"  # fallback

F_GEN_URL = "https://nxapi-znca-api.fancy.org.uk/api/znca/f"
F_GEN_URL_2 = "https://nxapi-znca-api.fancy.org.uk/api/znca/f"
F_GEN_OAUTH_URL = "https://nxapi-auth.fancy.org.uk/api/oauth/token"
F_GEN_OAUTH_client_id = "Orh4jxABP3D3jYaBFgL9Ug"
F_GEN_X_znca_Client_Version = "hio87-mJks_e9GNF"
F_GEN_is_encrypt = True  ## nxapi接口是否使用加密传递

F_USER_AGENT = f"nonebot_plugin_splatoon3_nso/{BOT_VERSION}"
APP_USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Pixel 7a) " \
                 "AppleWebKit/537.36 (KHTML, like Gecko) " \
                 "Chrome/120.0.6099.230 Mobile Safari/537.36"

# f api请求容量
fapi_rate = 2
# 限流器
rate_limiter = None


class GlobalRateLimiter:
    """全局限流器"""
    _instance = None
    _lock = asyncio.Lock()
    _semaphores: Dict[asyncio.AbstractEventLoop, asyncio.BoundedSemaphore] = WeakKeyDictionary()

    def __init__(self, rate: int = fapi_rate):
        self.rate = rate
        self._loop_lock = asyncio.Lock()  # 单独保护_semaphores

    async def acquire(self):
        """获取令牌，支持等待"""
        loop = asyncio.get_running_loop()
        async with self._loop_lock:
            if loop not in self._semaphores:
                # 使用BoundedSemaphore防止release次数过多
                self._semaphores[loop] = asyncio.BoundedSemaphore(self.rate)
        # nb_logger.info(f"get success,dict:{json.dumps(self.get_serializable_state())}")

        try:
            await self._semaphores[loop].acquire()
            return True
        except asyncio.CancelledError:
            # 如果任务被取消，确保释放令牌
            self._semaphores[loop].release()
            raise

    async def release(self):
        """释放令牌"""
        loop = asyncio.get_running_loop()
        async with self._loop_lock:
            if loop in self._semaphores:
                try:
                    self._semaphores[loop].release()
                except ValueError:
                    # 防止release次数超过acquire次数
                    pass
        # nb_logger.info(f"exit success,dict:{json.dumps(self.get_serializable_state())}")

    async def get_serializable_state(self) -> Dict[str, Any]:
        """获取可序列化的状态信息"""
        async with self._loop_lock:
            used = sum(self.rate - sem._value for sem in self._semaphores.values())
            return {
                "max_rate": self.rate,
                "used_permits": used,
                "available": max(0, self.rate - used),
                "active_loops": len(self._semaphores)
            }

    async def __aenter__(self):
        """进入上下文时获取令牌"""
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        """退出上下文时自动释放令牌"""
        await self.release()

    @classmethod
    async def get_instance(cls, rate: int = fapi_rate) -> 'GlobalRateLimiter':
        """获取单例"""
        if cls._instance is None:
            async with cls._lock:  # 双检锁保证线程安全
                if cls._instance is None:
                    cls._instance = cls(rate)
        return cls._instance


class S3S:
    _rate_limiter = None  # 延迟初始化

    def __init__(self, platform, user_id, _type="normal"):
        # self.req_client = get_or_init_client(platform, user_id, _type)
        self.r_user_id = ""  # 请求内部所使用的user_id,不是消息平台的user_id
        self.user_nickname = ""
        self.user_lang = "zh-CN"
        self.user_country = "JP"
        self.oauth_token = None

        # 负载均衡初始化
        f_url_lst = [F_GEN_URL, F_GEN_URL_2]
        # random.shuffle(f_url_lst)
        self.f_gen_url = f_url_lst[0]

        self.logger = nb_logger
        if _type == "cron":
            self.logger = nb_logger.bind(cron=True)

    def close(self):
        # self.req_client = None
        self.r_user_id = ""  # 请求内部所使用的user_id,不是消息平台的user_id
        self.user_nickname = ""
        self.user_lang = "zh-CN"
        self.user_country = "JP"
        self.oauth_token = None

    @staticmethod
    async def get_nsoapp_version(f_gen_url=None):
        """Fetches the current Nintendo Switch Online app version from f API or the Apple App Store and sets it globally."""
        if not f_gen_url:
            f_gen_url = F_GEN_URL
        global NSOAPP_VERSION
        if NSOAPP_VERSION != "unknown":  # already set
            return NSOAPP_VERSION
        else:
            try:  # try to get NSO version from f API
                f_conf_url = f_gen_url.replace("/f", "") + "/config"  # default endpoint for imink API
                f_conf_header = {"User-Agent": F_USER_AGENT}
                f_conf_rsp = await AsHttpReq.get(f_conf_url, headers=f_conf_header, timeout=10.0)
                f_conf_json = json.loads(f_conf_rsp.text)
                ver = f_conf_json["nso_version"]
                NSOAPP_VERSION = ver

                return NSOAPP_VERSION
            except:  # fallback to apple app store
                try:
                    page = await AsHttpReq.get("https://apps.apple.com/us/app/nintendo-switch-online/id1234806557", timeout=10.0)
                    soup = BeautifulSoup(page.text, 'html.parser')
                    elt = soup.find("p", {"class": "whats-new__latest__version"})
                    ver = elt.get_text().replace("Version ", "").strip()

                    NSOAPP_VERSION = ver
                    return NSOAPP_VERSION
                except:  # error with web request
                    pass

                return NSOAPP_VER_FALLBACK

    @staticmethod
    async def get_web_view_ver(bhead=None, gtoken=""):
        """Finds & parses the SplatNet 3 main.js file to fetch the current site version and sets it globally."""
        if bhead is None:
            bhead = []
        global WEB_VIEW_VERSION
        if WEB_VIEW_VERSION != "unknown":
            return WEB_VIEW_VERSION
        else:
            app_head = {
                'Upgrade-Insecure-Requests': '1',
                'Accept': '*/*',
                'DNT': '1',
                'X-AppColorScheme': 'DARK',
                'X-Requested-With': 'com.nintendo.znca',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-User': '?1',
                'Sec-Fetch-Dest': 'document'
            }
            app_cookies = {
                '_dnt': '1'  # Do Not Track
            }

            if bhead:
                app_head["User-Agent"] = bhead.get("User-Agent")
                app_head["Accept-Encoding"] = bhead.get("Accept-Encoding")
                app_head["Accept-Language"] = bhead.get("Accept-Language")
            if gtoken:
                app_cookies["_gtoken"] = gtoken  # X-GameWebToken

            try:
                home = await AsHttpReq.get(SPLATNET3_URL, headers=app_head, cookies=app_cookies, timeout=10.0)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                return WEB_VIEW_VER_FALLBACK

            if home.status_code != 200:
                return WEB_VIEW_VER_FALLBACK

            soup = BeautifulSoup(home.text, "html.parser")
            main_js = soup.select_one("script[src*='static']")

            if not main_js:  # failed to parse html for main.js file
                return WEB_VIEW_VER_FALLBACK

            main_js_url = SPLATNET3_URL + main_js.attrs["src"]

            app_head = {
                'Accept': '*/*',
                'X-Requested-With': 'com.nintendo.znca',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Dest': 'script',
                'Referer': SPLATNET3_URL  # sending w/o lang, na_country, na_lang params
            }
            if bhead:
                app_head["User-Agent"] = bhead.get("User-Agent")
                app_head["Accept-Encoding"] = bhead.get("Accept-Encoding")
                app_head["Accept-Language"] = bhead.get("Accept-Language")

            main_js_body = await AsHttpReq.get(main_js_url, headers=app_head, cookies=app_cookies, timeout=10.0)
            if main_js_body.status_code != 200:
                return WEB_VIEW_VER_FALLBACK

            pattern = r"\b(?P<revision>[0-9a-f]{40})\b[\S]*?void 0[\S]*?\"revision_info_not_set\"\}`,.*?=`(?P<version>\d+\.\d+\.\d+)-"
            match = re.search(pattern, main_js_body.text)
            if match is None:
                return WEB_VIEW_VER_FALLBACK

            version, revision = match.group("version"), match.group("revision")
            ver_string = f"{version}-{revision[:8]}"

            WEB_VIEW_VERSION = ver_string

            return WEB_VIEW_VERSION

    async def login_in(self):
        """登录步骤第一步
        Logs in to a Nintendo Account and returns a session_token."""

        auth_state = base64.urlsafe_b64encode(os.urandom(36))
        auth_code_verifier = base64.urlsafe_b64encode(os.urandom(32))
        auth_cv_hash = hashlib.sha256()
        auth_cv_hash.update(auth_code_verifier.replace(b'=', b''))
        auth_code_challenge = base64.urlsafe_b64encode(auth_cv_hash.digest())

        app_head = {
            'Host': 'accounts.nintendo.com',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': APP_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8n',
            'DNT': '1',
            'Accept-Encoding': 'gzip,deflate,br',
        }
        # 这里获取的auth_state 和 auth_code_challenge 都是bytes，request请求中会自动转换为str，httpx却没有这层处理，需要自己手动加上
        body = {
            'state': auth_state.decode('utf-8'),
            'redirect_uri': 'npf71b963c1b7b6d119://auth',
            'client_id': '71b963c1b7b6d119',
            'scope': 'openid user user.birthday user.mii user.screenName',
            'response_type': 'session_token_code',
            'session_token_code_challenge': auth_code_challenge.replace(b'=', b'').decode('utf-8'),
            'session_token_code_challenge_method': 'S256',
            'theme': 'login_form'
        }

        url = f"https://accounts.nintendo.com/connect/1.0.0/authorize?{urllib.parse.urlencode(body)}"
        post_login = url

        return post_login, auth_code_verifier

    async def login_in_2(self, use_account_url, auth_code_verifier):
        """登录步骤第二步"""
        while True:
            try:
                if use_account_url == "skip":
                    return "skip"
                match = re.search("de=(.*)&st", use_account_url)
                session_token_code = match.group(1)
                resp = await self.get_session_token(session_token_code, auth_code_verifier)
                session_token = resp["session_token"]
                return session_token
            except KeyboardInterrupt:
                print("\nBye!")
                return "skip"
            except AttributeError:
                print("Malformed URL. Please try again, or press Ctrl+C to exit.")
                return "skip"
            except KeyError:  # session_token not found
                print("\nThe URL has expired. Please log out and back into your Nintendo Account and try again.")
                print(f"get_session_token error,resp:{resp}")
                print(
                    f"get_session_token error,\nsession_token_code:{session_token_code},\nauth_code_verifier:{auth_code_verifier.replace(b'=', b'').decode('utf-8')},\nresp:{resp}")
                return "skip"
            except Exception as ex:
                print(f'ex: {ex}')
                return "skip"

    async def get_session_token(self, session_token_code, auth_code_verifier):
        """Helper function for log_in_2()."""

        nsoapp_version = await self.get_nsoapp_version()

        app_head = {
            'User-Agent': f'OnlineLounge/{nsoapp_version} NASDKAPI Android',
            'Accept-Language': 'en-US',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Host': 'accounts.nintendo.com',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip'
        }

        # 这里同样的auth_code_verifier同样为byte，需要手动转为str
        body = {
            'client_id': '71b963c1b7b6d119',
            'session_token_code': session_token_code,
            'session_token_code_verifier': auth_code_verifier.replace(b'=', b'').decode('utf-8')
        }

        url = 'https://accounts.nintendo.com/connect/1.0.0/api/session_token'
        r = await AsHttpReq.post(url, headers=app_head, data=body)
        session_token = json.loads(r.text)

        return session_token

    async def _get_id_token_and_user_info(self, session_token):
        """get_gtoken第一步"""
        # get_id_token
        app_head = {
            'Host': 'accounts.nintendo.com',
            'Accept-Encoding': 'gzip',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Connection': 'Keep-Alive',
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 14; Pixel 7a Build/UQ1A.240105.004)'
        }
        body = {
            'client_id': '71b963c1b7b6d119',
            'session_token': session_token,
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer-session-token'
        }
        url = "https://accounts.nintendo.com/connect/1.0.0/api/token"
        try:
            r = await AsHttpReq.post(url, headers=app_head, json=body)
            id_response = json.loads(r.text)
        except httpx.ConnectError:
            raise ValueError("NetConnectError")
        except httpx.ConnectTimeout:
            raise ValueError("NetConnectTimeout")
        except json.JSONDecodeError as e:
            raise ValueError("JSONDecodeError")
        except Exception as e:
            raise e

        if id_response.get('error') == 'invalid_grant':
            raise ValueError("invalid_grant")
        id_access_token = id_response.get("access_token")
        id_token = id_response.get("id_token")
        if not id_access_token:
            raise ValueError(f"resp error:{json.dumps(id_response)}")

        # get user info
        app_head = {
            'User-Agent': 'NASDKAPI; Android',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {id_access_token}',
            'Host': 'api.accounts.nintendo.com',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip'
        }

        url = "https://api.accounts.nintendo.com/2.0.0/users/me"
        try:
            r = await AsHttpReq.get(url, headers=app_head)
        except httpx.ConnectError:
            raise ValueError("NetConnectError")
        except httpx.ConnectTimeout:
            raise ValueError("NetConnectTimeout")
        except Exception as e:
            raise e
        user_info = json.loads(r.text)

        return id_token, user_info

    async def _get_access_token(self, id_token, user_info):
        """get_gtoken第二步"""
        # get access token
        self.user_nickname = user_info["nickname"]
        self.user_lang = user_info["language"]
        self.user_country = user_info["country"]
        self.r_user_id = user_info["id"]
        birthday = user_info["birthday"]
        parameter = {
            'language': self.user_lang,
            'naBirthday': birthday,
            'naCountry': self.user_country,
            'naIdToken': id_token,
            'f': '',
            'requestId': '',
            'timestamp': 0
        }
        body = {"parameter": parameter}
        url = "https://api-lp1.znc.srv.nintendo.net/v4/Account/Login"
        # 传递加密参数
        encrypt_token_request = {"url": url, "parameter": parameter}
        try:
            """
            encrypt_token_request 是一个三选一的结构体，提交给/v4/Account/Login，/v4/Game/GetWebServiceToken，/v4/Game/GetWebServiceToken的body结构传入一个就行
            """
            f, uuid, timestamp, encrypt_result = await self.f_api(id_token, 1, self.f_gen_url, self.r_user_id,
                                                                  encrypt_token_request=encrypt_token_request)
        except Exception as e:
            raise e

        nsoapp_version = await self.get_nsoapp_version()
        app_head = {
            'X-Platform': 'Android',
            'X-ProductVersion': nsoapp_version,
            'Content-Type': 'application/octet-stream' if F_GEN_is_encrypt else 'application/json; charset=utf-8',
            'Accept': 'application/octet-stream,application/json' if F_GEN_is_encrypt else 'application/json',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': f'com.nintendo.znca/{nsoapp_version}(Android/14)',
        }

        # nb_logger.info(f"headers:{app_head}")
        # nb_logger.info(f"body:{body}")

        try:
            content = base64.b64decode(encrypt_result)  # 加密数据还原为二进制
            znc_encrypt_data = await AsHttpReq.post(url, headers=app_head, content=content)
            # 解密返回数据
            decrypt_data = await self.f_decrypt_response(f_gen_url=self.f_gen_url, encrypted_data=znc_encrypt_data.content)
            decrypt_json = json.loads(decrypt_data.text)  # 返回数据包装在data内，还需要二次json解码
            splatoon_token = json.loads(decrypt_json["data"])
        except httpx.ConnectError:
            raise ValueError("NetConnectError")
        except httpx.ConnectTimeout:
            raise ValueError("NetConnectTimeout")
        except json.JSONDecodeError as e:
            raise ValueError("JSONDecodeError")
        except Exception as e:
            raise e

        if not splatoon_token:
            raise ValueError(f"resp error:{json.dumps(splatoon_token)}")

        try:
            # access_token过期时间3600s 即1h
            access_token = splatoon_token["result"]["webApiServerCredential"]["accessToken"]
            coral_user_id = splatoon_token["result"]["user"]["id"]
            # res里面含有各种用户信息，将其传输到splatoon层，并储存相关信息
            current_user = splatoon_token["result"]["user"]
        except:
            # retry once if 9403/9599 error from nintendo
            try:
                f, uuid, timestamp, encrypt_result = await self.f_api(id_token, 1, self.f_gen_url, self.r_user_id,
                                                                      encrypt_token_request=encrypt_token_request)
                body["parameter"]["f"] = f
                body["parameter"]["requestId"] = uuid
                body["parameter"]["timestamp"] = timestamp
                # Content-Length字段似乎不是必要的，或是httpx自动生成了，原来的字段是给request请求设置的
                # app_head["Content-Length"] = str(990 + len(f))
                url = "https://api-lp1.znc.srv.nintendo.net/v4/Account/Login"
                content = base64.b64decode(encrypt_result)
                znc_encrypt_data = await AsHttpReq.post(url, headers=app_head, content=content)
                # 解密返回数据
                decrypt_data = await self.f_decrypt_response(f_gen_url=self.f_gen_url, encrypted_data=znc_encrypt_data.content)
                decrypt_json = json.loads(decrypt_data.text)  # 返回数据包装在data内，还需要二次json解码
                splatoon_token = json.loads(decrypt_json["data"])
                access_token = splatoon_token["result"]["webApiServerCredential"]["accessToken"]
                coral_user_id = splatoon_token["result"]["user"]["id"]
                # res里面含有各种用户信息，将其传输到splatoon层，并储存相关信息
                current_user = splatoon_token["result"]["user"]
            except json.JSONDecodeError as e:
                raise ValueError("JSONDecodeError")
            except Exception:
                raise ValueError(f"resp error:{json.dumps(splatoon_token)}")

        return access_token, f, uuid, timestamp, coral_user_id, current_user

    async def _get_g_token(self, access_token, f, uuid, timestamp, coral_user_id):
        """get_gtoken第三步"""
        # get gtoken ,即 web service token
        nsoapp_version = await self.get_nsoapp_version()
        app_head = {
            'X-Platform': 'Android',
            'X-ProductVersion': nsoapp_version,
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/octet-stream' if F_GEN_is_encrypt else 'application/json; charset=utf-8',
            'Accept': 'application/octet-stream,application/json' if F_GEN_is_encrypt else 'application/json',
            'Accept-Encoding': 'gzip',
            'User-Agent': f'com.nintendo.znca/{nsoapp_version}(Android/14)'
        }
        parameter = {
            'id': 4834290508791808,
            'registrationToken': access_token,
            'requestId': '',
            'f': '',
            'timestamp': 0
        }
        body = {"parameter": parameter}
        url = "https://api-lp1.znc.srv.nintendo.net/v4/Game/GetWebServiceToken"
        # 传递加密参数
        encrypt_token_request = {"url": url, "parameter": parameter}
        try:
            """
            encrypt_token_request 是一个三选一的结构体，提交给/v4/Account/Login，/v4/Game/GetWebServiceToken，/v4/Game/GetWebServiceToken的body结构传入一个就行
            """
            f, uuid, timestamp, encrypt_result = await self.f_api(access_token, 2, self.f_gen_url, self.r_user_id,
                                                                  coral_user_id=coral_user_id,
                                                                  encrypt_token_request=encrypt_token_request)
        except Exception as e:
            raise e
        try:
            content = base64.b64decode(encrypt_result)  # 加密数据还原为二进制
            znc_encrypt_data = await AsHttpReq.post(url, headers=app_head, content=content)
            # 解密返回数据
            decrypt_data = await self.f_decrypt_response(f_gen_url=self.f_gen_url, encrypted_data=znc_encrypt_data.content)
            decrypt_json = json.loads(decrypt_data.text)  # 返回数据包装在data内，还需要二次json解码
            web_service_resp = json.loads(decrypt_json["data"])
        except httpx.ConnectError:
            raise ValueError("NetConnectError")
        except httpx.ConnectTimeout:
            raise ValueError("NetConnectTimeout")
        except json.JSONDecodeError as e:
            raise ValueError("JSONDecodeError")
        except Exception as e:
            raise e

        try:
            web_service_token = web_service_resp["result"]["accessToken"]
        except:
            # retry once if code 9403/9599 error from nintendo
            self.logger.debug(f"retry once if code 9403/9599 error from nintendo")
            try:
                f, uuid, timestamp = await self.f_api(access_token, 2, self.f_gen_url, self.r_user_id,
                                                      coral_user_id=coral_user_id,
                                                      encrypt_token_request=encrypt_token_request)
                body["parameter"]["f"] = f
                body["parameter"]["requestId"] = uuid
                body["parameter"]["timestamp"] = timestamp
                url = "https://api-lp1.znc.srv.nintendo.net/v4/Game/GetWebServiceToken"
                r = await AsHttpReq.post(url, headers=app_head, json=body)
                web_service_resp = json.loads(r.text)
                web_service_token = web_service_resp["result"]["accessToken"]
            except:
                self.logger.warning(f"f_api retry error:resp:{json.dumps(web_service_resp)}")
                if web_service_resp.get('errorMessage') == 'Membership required error.':
                    raise ValueError(f"Membership required error.|{self.user_nickname}")
                return

        # web_service_token 有效期为10800秒 3h
        return web_service_token

    async def get_gtoken(self, session_token):
        """Provided the session_token, returns a GameWebToken and account info."""
        # get_id_tokenaccess_token, f, uuid, timestamp, coral_user_id
        await self.get_nsoapp_version()
        try:
            id_token, user_info = await self._get_id_token_and_user_info(session_token)
            if not user_info or not id_token:
                raise ValueError(f"no id_token or user_info")
        except Exception as e:
            self.logger.warning(f"get_id_token_and_user_info error:{e}")
            raise e

        try:
            access_token, f, uuid, timestamp, coral_user_id, current_user = await self._get_access_token(id_token,
                                                                                                         user_info)
            if not access_token:
                raise ValueError(f"no access_token")
            if not f:
                raise ValueError(f"no f")
        except Exception as e:
            self.logger.warning(f"get_access_token error:{e}")
            raise e
        try:
            g_token = await self._get_g_token(access_token, f, uuid, timestamp, coral_user_id)
            if not g_token:
                raise ValueError(f"no g_token")
        except Exception as e:
            self.logger.warning(f"get_g_token error:{e}")
            raise e

        return access_token, g_token, self.user_nickname, self.user_lang, self.user_country, current_user

    async def get_bullet(self, user_id, g_token):
        """Given a gtoken, returns a bulletToken."""

        app_head = {
            'Content-Length': '0',
            'Content-Type': 'application/json',
            'Accept-Language': self.user_lang,
            'User-Agent': APP_USER_AGENT,
            'X-Web-View-Ver': await self.get_web_view_ver(),
            'X-NACOUNTRY': self.user_country,
            'Accept': '*/*',
            'Origin': SPLATNET3_URL,
            'X-Requested-With': 'com.nintendo.znca'
        }
        app_cookies = {
            '_gtoken': g_token,  # X-GameWebToken
            '_dnt': '1'  # Do Not Track
        }
        url = f'{SPLATNET3_URL}/api/bullet_tokens'
        r = await AsHttpReq.post(url, headers=app_head, cookies=app_cookies)
        # self.logger.error(f'{user_id} get_bullet error. {r.status_code}，res:{str(r.content.decode("utf-8"))}')
        # self.logger.info(f'url:{url}\nheaders: {json.dumps(app_head)},\ncookies: {json.dumps(app_cookies)}')

        try:
            # bullet_token过期时间7200s 即2h
            r_json = json.loads(r.text)
            bullet_token = r_json['bulletToken']
            return bullet_token
        except (json.decoder.JSONDecodeError, json.JSONDecodeError) as e:
            self.logger.exception(f'{user_id} get_bullet error. {r.status_code}，res:{r.text}')
            if r.status_code == 401:
                self.logger.exception(
                    "Unauthorized error (ERROR_INVALID_GAME_WEB_TOKEN). Cannot fetch tokens at this time.")
            elif r.status_code == 403:
                self.logger.exception("Forbidden error (ERROR_OBSOLETE_VERSION). Cannot fetch tokens at this time.")
            elif r.status_code == 204:  # No Content, USER_NOT_REGISTERED
                self.logger.exception("Cannot access SplatNet 3 without having played online.")
            elif r.status_code == 499:  # 鱿鱼圈封禁
                self.logger.exception(f"user_id:{user_id} has be banned")
                raise ValueError(f"user_id:{user_id} has be banned")
            raise ValueError(f"user_id:{user_id} get_bullet error. status_code:{r.status_code}")
        except Exception as e:
            self.logger.warning(f"user_id:{user_id} get_bullet error:{e}")

    async def f_api_clent_auth2_register(self):
        # api docs see https://github.com/samuelthomas2774/nxapi-znca-api/blob/docs/docs/api.md
        # oauth2 web see https://nxapi-auth.fancy.org.uk/oauth/clients
        api_response = None
        try:
            api_head = {
                'User-Agent': F_USER_AGENT,
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            api_body = {
                'grant_type': 'client_credentials',
                'client_id': F_GEN_OAUTH_client_id,
                'scope': 'ca:gf ca:er ca:dr'
            }

            # self.logger.info(f"f body:{json.dumps(api_body)}")
            api_response = await AsHttpReq.post(F_GEN_OAUTH_URL, data=api_body, headers=api_head)
            # self.logger.info(f"f res_text:{api_response.text}")

            resp: dict = json.loads(api_response.text)

            access_token = resp.get("access_token")
            self.oauth_token = access_token
            return True
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            if isinstance(e, httpx.ConnectError):
                return "NetConnectError"
            elif isinstance(e, httpx.ConnectTimeout):
                return "NetConnectTimeout"

        except Exception as e:
            # self.logger.error(f"Error during f generation: Error {e}.")
            try:  # if api_response never gets set
                if api_response and api_response.text:
                    if "html" in api_response.text:
                        error = "html网页错误"
                    else:
                        error = api_response.text
                    self.logger.warning(
                        f"Error during oauth register\nres:{error}")
                    return f"resp error:{error}"
                else:
                    self.logger.warning(
                        f"Error during oauth register status_code:{api_response.status_code}")
                    return f"resp error:status_code:{api_response.status_code}"

            except Exception as e:
                self.logger.error(f"Error during oauth register: Error {e}.")
                # 一般是status_code都获取不到
                return None

    async def f_api(self, *args, **kwargs):
        """限流版f_api，支持等待和重试"""
        if self._rate_limiter is None:
            self._rate_limiter = await GlobalRateLimiter.get_instance(fapi_rate)

        try:
            async with self._rate_limiter:
                return await self._real_f_api(*args, **kwargs)
        except asyncio.CancelledError:
            # 如果任务被取消，重新抛出异常
            raise
        except Exception as e:
            self.logger.error(f"Error in f_api: {str(e)}")
            raise

    async def _real_f_api(self, access_token, step, f_gen_url, r_user_id, coral_user_id=None,
                          encrypt_token_request=None):
        res = await self.call_f_api(access_token, step, f_gen_url, r_user_id, coral_user_id,
                                    encrypt_token_request=encrypt_token_request)
        if isinstance(res, tuple):
            return res
        else:
            # 12.20日 只有nxapi可用，禁用重试机制 return None
            return None

        # 判断重试时的对象名称以及f地址
        if self.f_gen_url == F_GEN_URL:
            now_f_str = "F_URL"
            next_f_str = "F_URL_2"
            next_f_url = F_GEN_URL_2
        else:
            now_f_str = "F_URL_2"
            next_f_str = "F_URL"
            next_f_url = F_GEN_URL

        if not res:
            # 无响应结果
            self.logger.warning(f"{now_f_str} no res，try {next_f_str} again")
        elif isinstance(res, str):
            # 错误信息
            # 改为另一个f接口并重新请求一次
            if "NetConnectError" in res:
                self.logger.warning(f"{now_f_str} ConnectError，try {next_f_str} again")
            elif "NetConnectTimeout" in res:
                self.logger.warning(f"{now_f_str} ConnectTimeout，try {next_f_str} again")
            else:
                error = res
                if "html" in error:
                    error = "html网页错误"
                self.logger.warning(f"{now_f_str} res Error，try {next_f_str} again, Error:{error}")

        self.f_gen_url = next_f_url
        res = await self.call_f_api(access_token, step, self.f_gen_url, r_user_id, coral_user_id,
                                    encrypt_token_request=encrypt_token_request)
        if isinstance(res, tuple):
            return res
        else:
            error = res
            if "html" in error:
                error = "html网页错误"
            self.logger.warning(f"{next_f_str} Both Error: {error}")
            return None

    async def call_f_api(self, access_token, step, f_gen_url, r_user_id, coral_user_id=None,
                         encrypt_token_request=None):
        """Passes naIdToken & user ID to f generation API (default: imink) & fetches response (f token, UUID, timestamp)."""
        api_head = {}
        api_body = {}
        api_response = None
        if not self.oauth_token:
            # oauth token 过期,重新申请token
            await self.f_api_clent_auth2_register()
        try:
            api_head = {
                'User-Agent': F_USER_AGENT,
                'Content-Type': 'application/json; charset=utf-8',
                'Accept': 'application/json',
                'X-znca-Platform': 'Android',
                'X-znca-Version': NSOAPP_VERSION,
                'X-znca-Client-Version': F_GEN_X_znca_Client_Version,
                'Authorization': 'Bearer ' + self.oauth_token,

            }
            api_body = {  # 'timestamp' & 'request_id' (uuid v4) set automatically
                'token': access_token,
                'hash_method': step,  # 1 = coral (NSO) token, 2 = webservicetoken
                'na_id': r_user_id
            }
            if encrypt_token_request:
                api_body['encrypt_token_request'] = encrypt_token_request

            if step == 2 and coral_user_id is not None:
                api_body["coral_user_id"] = str(coral_user_id)

            # self.logger.info(f"f body:{json.dumps(api_body)}")
            api_response = await AsHttpReq.post(f_gen_url, json=api_body, headers=api_head)
            # self.logger.info(f"f res_text:{api_response.text}")

            resp: dict = json.loads(api_response.text)
            if "error" in resp and "error_message" in resp:
                self.logger.debug(
                    f"Error during f generation: \n{f_gen_url}  \nres_text:{api_response.text}")
                return f"f resp status_code:{api_response.status_code},error:{api_response.text}"
            error = resp.get("error")
            error_message = resp.get("error_message")
            if error == "invalid_token" and error_message == "Token expired":
                # oauth token 过期,重新申请token
                await self.f_api_clent_auth2_register()
                return await self.call_f_api(access_token=access_token, step=step, f_gen_url=f_gen_url,
                                             r_user_id=r_user_id, coral_user_id=coral_user_id)
            f = resp.get("f")
            uuid = resp.get("request_id")
            timestamp = resp.get("timestamp")
            encrypted_token_request = resp.get("encrypted_token_request")
            return f, uuid, timestamp, encrypted_token_request
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            if isinstance(e, httpx.ConnectError):
                return "NetConnectError"
            elif isinstance(e, httpx.ConnectTimeout):
                return "NetConnectTimeout"

        except Exception as e:
            # self.logger.error(f"Error during f generation: Error {e}.")
            try:  # if api_response never gets set
                if api_response and api_response.text:
                    error = api_response.text
                    if "html" in error:
                        error = "html网页错误"
                    self.logger.warning(
                        f"Error during f generation: {f_gen_url}\nres:{error}")
                else:
                    self.logger.warning(
                        f"Error during f generation: \n{f_gen_url}  status_code:{api_response.status_code}")
                return f"resp error:{api_response.text}"
            except Exception as e:
                self.logger.error(f"Error during f generation: Error {e}.")
                # 一般是status_code都获取不到
                return None

    async def f_encrypt_request(self, api_url: str, access_token: str, body_data: dict,
                                f_gen_url: str = F_GEN_URL) -> httpx.Response | None:
        """nxapi 加密数据"""
        api_head = {
            'User-Agent': F_USER_AGENT,
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json; charset=utf-8',
            'X-znca-Platform': 'Android',
            'X-znca-Version': await self.get_nsoapp_version(),
            'X-znca-Client-Version': F_GEN_X_znca_Client_Version,
        }
        if self.oauth_token:
            api_head['Authorization'] = f"Bearer {self.oauth_token}"
        api_body = {
            'url': api_url,
            'token': access_token,
            'data': json.dumps(body_data)
        }
        url = f_gen_url.replace("/f", "/encrypt-request")

        try:
            api_response = await AsHttpReq.post(url, json=api_body, headers=api_head)
            return api_response
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            if isinstance(e, httpx.ConnectError):
                return "NetConnectError"
            elif isinstance(e, httpx.ConnectTimeout):
                return "NetConnectTimeout"
        except Exception as e:
            # self.logger.error(f"Error during f generation: Error {e}.")
            try:  # if api_response never gets set
                if api_response and api_response.text:
                    error = api_response.text
                    if "html" in error:
                        error = "html网页错误"
                    self.logger.warning(
                        f"Error during f generation encrypt: {f_gen_url}\nres:{error}")
                else:
                    self.logger.warning(
                        f"Error during f generation encrypt: \n{f_gen_url}  status_code:{api_response.status_code}")
                return f"resp error:{api_response.text}"
            except Exception as e:
                self.logger.error(f"Error during f generation encrypt: Error {e}.")
                # 一般是status_code都获取不到
                return None

    async def f_decrypt_response(self, encrypted_data: bytes, f_gen_url: str = F_GEN_URL):
        """nxapi 解密数据"""
        api_body = {
            "data": base64.b64encode(encrypted_data).decode("utf-8")  # 必传：Base64编码的密文
        }
        api_head = {
            'User-Agent': F_USER_AGENT,
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json; charset=utf-8',
            'X-znca-Platform': 'Android',
            'X-znca-Version': NSOAPP_VERSION,
            'X-znca-Client-Version': F_GEN_X_znca_Client_Version,
        }
        if self.oauth_token:
            api_head['Authorization'] = f"Bearer {self.oauth_token}"
        url = f_gen_url.replace("/f", "/decrypt-response")

        try:
            api_response = await AsHttpReq.post(url, json=api_body, headers=api_head)
            return api_response
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            if isinstance(e, httpx.ConnectError):
                return "NetConnectError"
            elif isinstance(e, httpx.ConnectTimeout):
                return "NetConnectTimeout"
        except Exception as e:
            # self.logger.error(f"Error during f generation: Error {e}.")
            try:  # if api_response never gets set
                if api_response and api_response.text:
                    error = api_response.text
                    if "html" in error:
                        error = "html网页错误"
                    self.logger.warning(
                        f"Error during f generation decrypt: {f_gen_url}\nres:{error}")
                else:
                    self.logger.warning(
                        f"Error during f generation decrypt: \n{f_gen_url}  status_code:{api_response.status_code}")
                return f"resp error:{api_response.text}"
            except Exception as e:
                self.logger.error(f"Error during f generation decrypt: Error {e}.")
                # 一般是status_code都获取不到
                return None

    @staticmethod
    def is_jwt_token_valid(token: str, leeway: int = 0) -> bool:
        """
        仅校验 JWT Token 是否格式有效且未过期（不验证签名，无需 secret）

        Args:
            token: 待校验的 JWT Token 字符串
            leeway: 时间误差容忍值（秒），解决客户端/服务器时间不一致问题

        Returns:
            bool: Token 格式有效 + 未过期 → 返回 True；过期/格式无效 → 返回 False
        """
        # 空 Token 直接判定无效
        if not token or not isinstance(token, str):
            return False

        try:
            # 核心逻辑：关闭签名验证（verify_signature=False），仅解析 payload 并校验过期
            # options 配置：
            # - verify_signature=False：跳过签名验证（无需 secret）
            # - verify_exp=True：强制校验过期时间（默认开启，显式声明更清晰）
            jwt.decode(
                jwt=token,
                key="",  # 无 secret 时传空字符串即可（签名验证已关闭）
                algorithms=["HS256", "RS256", "ES256"],  # 兼容常见算法（无需匹配实际算法）
                leeway=leeway,
                options={
                    "verify_signature": False,
                    "verify_exp": True
                }
            )
            return True

        except ExpiredSignatureError:
            # Token 已过期
            return False
        except DecodeError:
            # Token 格式错误（如不是 JWT 格式、缺少 . 分隔符、base64 解码失败等）
            return False
        except InvalidTokenError:
            # 其他无效场景（如 payload 无 exp 字段但开启了过期校验、字段格式错误等）
            return False
        except Exception:
            # 兜底：任何未预期的异常都判定为无效
            return False


def init_global_nso_version_and_web_view_version():
    """全局变量NSOAPP_VERSION 和 WEB_VIEW_VERSION 置空"""
    global NSOAPP_VERSION
    global WEB_VIEW_VERSION
    NSOAPP_VERSION = "unknown"
    WEB_VIEW_VERSION = "unknown"


if __name__ == "__main__":
    print("This program cannot be run alone. See https://github.com/frozenpandaman/s3s")
    sys.exit(0)
