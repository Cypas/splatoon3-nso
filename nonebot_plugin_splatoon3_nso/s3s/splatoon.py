import asyncio
import base64
import gc
import json
import time
import uuid

import httpx
from nonebot import Bot, logger as nb_logger
from nonebot.internal.adapter import Event

from .utils import gen_graphql_body, translate_rid, GRAPHQL_URL
from .iksm import APP_USER_AGENT, SPLATNET3_URL, S3S
from ..data.utils import GlobalUserInfo
from ..handle.send_msg import bot_send, notify_to_private, notify_to_channel
from ..data.data_source import dict_get_or_set_user_info, model_get_or_set_user, model_get_another_account_user, \
    global_user_info_dict, global_cron_user_info_dict, model_get_temp_image_path
from ..utils import get_msg_id, get_or_init_client, AsHttpReq
from ..utils.redis import rset_gtoken, rget_gtoken


class UserDBInfo:
    def __init__(self, db_id, user_name, game_name, game_sp_id, create_time, report_notify, push_cnt, cmd_cnt):
        self.db_id = db_id
        self.user_name = user_name
        self.game_name = game_name
        self.game_sp_id = game_sp_id
        self.create_time = create_time
        self.report_notify = report_notify
        self.push_cnt = push_cnt
        self.cmd_cnt = cmd_cnt


class Splatoon:
    def __init__(self, bot: Bot, event: Event, user_info: GlobalUserInfo, _type="normal"):
        self.bot = bot
        self.event = event
        self.platform = user_info.platform or "no_platform"
        self.user_id = user_info.user_id or "no_user_id"
        self.user_name = user_info.user_name
        self.nsa_id = user_info.nsa_id
        self.ns_name = user_info.ns_name
        self.ns_friend_code = user_info.ns_friend_code
        self.session_token = user_info.session_token
        self.user_lang = "zh-CN"
        self.user_country = "JP"
        self.bullet_token = ""
        self.g_token = ""
        self.access_token = ""
        self.s3s = S3S(self.platform, self.user_id, _type=_type)
        self.dict_type = _type
        # self.req_client = user_info.req_client or get_or_init_client(self.platform, self.user_id, _type=_type)
        self.logger = nb_logger
        if _type == "cron":
            self.logger = nb_logger.bind(cron=True)

        user = model_get_or_set_user(self.platform, self.user_id)
        if user:
            self.bullet_token = user.bullet_token
            self.g_token = user.g_token
            self.access_token = user.access_token
            self.user_db_info = UserDBInfo(str(user.id) or "0",
                                           user.user_name or "no user name",
                                           user.game_name or "no game name",
                                           user.game_sp_id or "",
                                           user.create_time,
                                           user.report_notify,
                                           user.push_cnt or 0,
                                           user.cmd_cnt or 0)

    def reload_tokens(self):
        """重载token"""
        user = model_get_or_set_user(self.platform, self.user_id)
        if user:
            self.bullet_token = user.bullet_token
            self.g_token = user.g_token
            self.access_token = user.access_token

    def set_user_info(self, **kwargs):
        """修改user信息"""
        # 修改自身类的值
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        # 修改全局字典
        dict_get_or_set_user_info(self.platform, self.user_id, _type=self.dict_type, **kwargs)

    async def refresh_gtoken_and_bullettoken(self, skip_access=True) -> bool:
        """刷新gtoken 和 bullettoken"""
        # 跨线程重载token
        self.reload_tokens()
        msg_id = get_msg_id(self.platform, self.user_id)
        new_access_token, new_g_token, new_bullet_token, user_lang, user_country = \
            "", "", "", self.user_lang, self.user_country
        game_sp_id = self.user_db_info.game_sp_id
        redis_g_token = ""
        current_user = {}

        if skip_access and game_sp_id:
            # 默认跳过access请求看redis是否有数据
            redis_g_token = await rget_gtoken(game_sp_id)
        if redis_g_token:
            new_g_token = redis_g_token
        else:
            try:
                # user_nickname为任天堂官网账号用户名，没有参考价值
                new_access_token, new_g_token, user_nickname, user_lang, user_country, current_user = \
                    await self.s3s.get_gtoken(self.session_token)
                if game_sp_id and new_g_token:
                    # redis set g_token
                    await rset_gtoken(game_sp_id, new_g_token)
            except Exception as e:
                self.logger.warning(f'{self.user_db_info.db_id},{msg_id} refresh_g_and_b_token error. reason:{e}')
                if self.user_db_info:
                    user = self.user_db_info
                    if 'invalid_grant' in str(e):
                        # 无效登录凭证
                        self.logger.warning(
                            f'invalid_grant_user: db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}')
                        self.set_user_info(session_token=None)
                        # 待发送文本
                        msg = f"喷3账号 {user.game_name or ''} 登录过期，一般是修改密码后登录才会过期，请发送/login 重新登录"
                        if self.bot and self.event:
                            # 来自用户主动请求
                            await bot_send(self.bot, self.event, msg)
                        else:
                            # 来自定时任务
                            if user.report_notify:
                                try:
                                    await notify_to_private(self.platform, self.user_id, msg)
                                except Exception as e:
                                    self.logger.warning(
                                        f'{self.user_db_info.db_id},msg_id:{msg_id} private notice error: {e}')
                            raise ValueError('invalid_grant')
                        return False
                    elif "Membership required" in str(e):
                        # 会员过期
                        self.logger.warning(
                            f"membership_required: db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}")
                        # 切割 会员过期 警告信息
                        nickname = str(e).split('|')[1] or ""
                        # 待发送文本
                        msg = f"喷3账号 {nickname} nso会员过期"
                        if self.bot and self.event:
                            msg += ",无法使用nso查询功能"
                            self.logger.warning(f'db_id:{user.db_id},membership_required notify')
                            # 来自用户主动请求
                            await bot_send(self.bot, self.event, msg)
                        else:
                            msg += ",无法更新日报"
                            # msg += "\n/report_notify close 关闭每日日报推送"
                            # 来自定时任务
                            # if user.report_notify:
                            #     await notify_to_private(self.platform, self.user_id, msg)

                            raise ValueError('Membership required')
                        return False
                return False

        if new_g_token:
            try:
                # 获取bullettoken
                new_bullet_token = await self.s3s.get_bullet(self.user_db_info.db_id, new_g_token)
                if not new_bullet_token:
                    raise ValueError(f"no new_bullet_token")
                user = dict_get_or_set_user_info(self.platform, self.user_id, _type=self.dict_type, user_agreement=1)
            except Exception as e:
                msg_id = get_msg_id(self.platform, self.user_id)
                if "has be banned" in str(e):
                    # 鱿鱼圈封禁
                    user = dict_get_or_set_user_info(self.platform, self.user_id, _type=self.dict_type,
                                                     user_agreement=-1)
                    msg = f"喷3账号 {user.game_name or ''} 鱿鱼圈被封禁，无法使用相关查询，一般会在一个月后自动解封,你可以加入q群756026315与其他被封禁用户交流"
                    if self.bot and self.event:
                        # 来自用户主动请求
                        await bot_send(self.bot, self.event, msg)
                    await notify_to_channel(
                        f"新的鱿鱼圈封禁用户:\n"
                        f"db_id:{self.user_db_info.db_id},msg_id:{msg_id},\n"
                        f"sp_id:{self.user_db_info.game_sp_id or ''},\n"
                        f"push_cnt:{self.user_db_info.push_cnt},cmd_cnt:{self.user_db_info.cmd_cnt},")

                    # 查询其他同绑账号
                    users = model_get_another_account_user(self.platform, self.user_id)
                    if len(users) > 0:
                        for u in users:
                            # 如果存在全局缓存，也更新缓存数据
                            key = get_msg_id(u.platform, u.user_id)
                            user_info = global_user_info_dict.get(key)
                            if user_info:
                                # 更新缓存数据
                                dict_get_or_set_user_info(u.platform, u.user_id, user_agreement=-1)
                            else:
                                # 更新数据库数据
                                model_get_or_set_user(u.platform, u.user_id, user_agreement=-1)

                            # 通知同绑账号调用情况
                            await notify_to_channel(
                                f"{self.user_db_info.db_id}同绑用户:\n"
                                f"db_id:{u.id},msg_id:{key},\n"
                                f"push_cnt:{u.push_cnt},cmd_cnt:{u.cmd_cnt},")

                    raise e

                else:
                    self.logger.warning(
                        f'{msg_id} get g_token success,get bullet_token error,start try again.reason:{e}')
                    new_bullet_token = await self.s3s.get_bullet(self.user_db_info.db_id, new_g_token)
        # 刷新值
        if new_g_token and new_bullet_token:
            if current_user:
                nsa_id = current_user.get("nsaId")
                my_icon_url = current_user['imageUri']
                my_icon = await model_get_temp_image_path('my_icon_by_nsa_id', nsa_id, my_icon_url)
                ns_name = current_user['name']
                ns_friend_code = current_user['links']['friendCode']['id']
                self.set_user_info(access_token=new_access_token, g_token=new_g_token, bullet_token=new_bullet_token,
                                   nsa_id=nsa_id, ns_name=ns_name, ns_friend_code=ns_friend_code)
            else:
                # 更新token和用户信息
                self.set_user_info(access_token=new_access_token, g_token=new_g_token, bullet_token=new_bullet_token)
            # 刷新其他同绑定账号
            self.refresh_another_account()
            self.logger.info(f'{self.user_db_info.db_id},{msg_id} tokens updated.')
            self.logger.debug(f'new access_token: {new_access_token}')
            self.logger.debug(f'new g_token: {new_g_token}')
            self.logger.debug(f'new bullet_token: {new_bullet_token}')
            return True
        return False

    def refresh_another_account(self):
        # 刷新同一game_sp_id的其他账号
        platform = self.platform
        user_id = self.user_id
        users = model_get_another_account_user(platform, user_id)
        if len(users) > 0:
            for u in users:
                msg_id = get_msg_id(u.platform, u.user_id)
                self.logger.debug(f'another_account {u.id},{msg_id} tokens updated.')
                # 如果存在全局缓存，也更新缓存数据
                key = get_msg_id(u.platform, u.user_id)
                user_info = global_user_info_dict.get(key)
                if user_info:
                    # 更新缓存数据
                    dict_get_or_set_user_info(u.platform, u.user_id, access_token=self.access_token,
                                              g_token=self.g_token, bullet_token=self.bullet_token, user_agreement=1,
                                              nsa_id=self.nsa_id, ns_name=self.ns_name,
                                              ns_friend_code=self.ns_friend_code)
                else:
                    # 更新数据库数据
                    model_get_or_set_user(u.platform, u.user_id, access_token=self.access_token,
                                          g_token=self.g_token, bullet_token=self.bullet_token, user_agreement=1,
                                          nsa_id=self.nsa_id, ns_name=self.ns_name,
                                          ns_friend_code=self.ns_friend_code)

    async def head_bullet(self, force_lang=None, force_country=None):
        """为含有bullet_token的请求拼装header"""
        if force_lang:
            lang = force_lang
            country = force_country
        else:
            lang = self.user_lang
            country = self.user_country

        graphql_head = {
            'Authorization': f'Bearer {self.bullet_token}',
            'Accept-Language': lang,
            'User-Agent': APP_USER_AGENT,
            'X-Web-View-Ver': await S3S.get_web_view_ver(),
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Origin': SPLATNET3_URL,
            'X-Requested-With': 'com.nintendo.znca',
            'Referer': f'{SPLATNET3_URL}/?lang={lang}&na_country={country}&na_lang={lang}',
            'Accept-Encoding': 'gzip, deflate'
        }
        return graphql_head

    async def test_page(self, multiple=False) -> bool:
        """主页(测试访问页面) """
        # 跨线程重载token
        self.reload_tokens()
        data = gen_graphql_body(translate_rid["HomeQuery"], "naCountry", "JP")

        msg_id = get_msg_id(self.platform, self.user_id)
        if not self.bullet_token or not self.g_token:
            # 首次请求如果为空时
            self.logger.info(f'{msg_id} tokens is None,start refresh tokens soon')
            # 更新token提醒一下用户
            if not multiple and self.bot and self.event:
                await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")

            success = await self.refresh_gtoken_and_bullettoken()
            if success:
                self.logger.info(f'{msg_id} refresh tokens complete，try again')
            else:
                self.logger.error(f'{msg_id} refresh tokens fail, return False')
                return False

        # t = time.time()
        headers = await self.head_bullet()
        cookies = dict(_gtoken=self.g_token)
        test = await AsHttpReq.post(GRAPHQL_URL, data=data, headers=headers, cookies=cookies)

        if test.status_code != 200:
            if test.status_code == 401:
                # 更新token提醒一下用户
                if not multiple and self.bot and self.event:
                    await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                try:
                    self.logger.info(
                        f'{self.user_db_info.db_id},{msg_id},{self.user_name},{self.user_db_info.game_name} tokens expired,start refresh tokens soon')
                    success = await self.refresh_gtoken_and_bullettoken()
                    if success:
                        self.logger.info(
                            f'{self.user_db_info.db_id},{msg_id},{self.user_name},{self.user_db_info.game_name} refresh tokens complete，try again')
                        return True
                    else:
                        self.logger.error(
                            f'{self.user_db_info.db_id},{msg_id},{self.user_name},{self.user_db_info.game_name} refresh tokens fail, return False')
                        return False
                except ValueError as e:
                    # 定时任务各种预期错误
                    raise e
                except Exception as e:
                    self.logger.error(
                        f'{self.user_db_info.db_id},{msg_id},{self.user_name},{self.user_db_info.game_name} refresh tokens fail,reason:{e}')
                    return False
            self.logger.error(
                f'{self.user_db_info.db_id},{msg_id},{self.user_name},{self.user_db_info.game_name} page test fail,status_code:{test.status_code},res:{test.text}'
                f'\ndata:{data}\nheaders:{headers}\ncookies:{cookies}')
            return False
        else:
            return True

    async def request(self, data, multiple=False, force_lang=None, force_country=None, return_json=True):
        # 跨线程重载token
        self.reload_tokens()
        res = ''
        msg_id = get_msg_id(self.platform, self.user_id)
        try:
            if not self.bullet_token or not self.g_token:
                # 首次请求如果为空时
                self.logger.info(f'{self.user_db_info.db_id},{msg_id} tokens is None,start refresh tokens soon')
                # 更新token提醒一下用户
                if not multiple and self.bot and self.event:
                    await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")

                success = await self.refresh_gtoken_and_bullettoken()
                if success:
                    self.logger.info(f'{self.user_db_info.db_id},{msg_id} refresh tokens complete，try again')
                else:
                    self.logger.error(f'{self.user_db_info.db_id},{msg_id} refresh tokens fail, return None')
                    return None
            t = time.time()
            res = await AsHttpReq.post(GRAPHQL_URL, data=data,
                                             headers=await self.head_bullet(),
                                             cookies=dict(_gtoken=self.g_token))
            t2 = f'{time.time() - t:.3f}'
            self.logger.debug(f'_request: {t2}s')
            self.logger.debug(f'data:{data} res:{res.text}')
            if res.status_code != 200:
                # multiple请求不再刷新token，以免重复报错
                if res.status_code == 401 and not multiple:
                    # 更新token提醒一下用户
                    if self.bot and self.event:
                        await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                    try:
                        self.logger.info(f'{self.user_db_info.db_id},{msg_id} tokens expired,start refresh tokens soon')
                        success = await self.refresh_gtoken_and_bullettoken()
                        if success:
                            self.logger.info(f'{self.user_db_info.db_id},{msg_id} refresh tokens complete，try again')
                        else:
                            self.logger.error(f'{self.user_db_info.db_id},{msg_id} refresh tokens fail, return None')
                            return None
                    except Exception as e:
                        self.logger.error(f'{self.user_db_info.db_id},{msg_id} refresh tokens fail,reason:{e}')
                    try:
                        t = time.time()
                        res = await AsHttpReq.post(GRAPHQL_URL, data=data,
                                                         headers=await self.head_bullet(),
                                                         cookies=dict(_gtoken=self.g_token))
                        t2 = f'{time.time() - t:.3f}'
                        self.logger.debug(f'_request: {t2}s')
                        if return_json:
                            return res.json()
                        else:
                            return res
                    except Exception as e:
                        self.logger.error(
                            f'{self.user_db_info.db_id},{msg_id} _request sp3net fail,reason:{e},res:{res.text}, start retry...')
                        try:
                            res = await AsHttpReq.post(GRAPHQL_URL, data=data,
                                                             headers=await self.head_bullet(),
                                                             cookies=dict(_gtoken=self.g_token))
                            if return_json:
                                return res.json()
                            else:
                                return res
                        except Exception as e:
                            self.logger.error(
                                f'{self.user_db_info.db_id},{msg_id} _request sp3net twice fail,reason:{e},res:{res.text}')
                            if return_json:
                                return None
                            else:
                                return res
                else:
                    if return_json:
                        return None
                    else:
                        return res
            else:
                if return_json:
                    return res.json()
                else:
                    return res
        except httpx.ConnectError:
            self.logger.warning(f'{self.user_db_info.db_id},{msg_id} _request error: connectError')
            raise ValueError('NetConnectError')
        except httpx.ConnectTimeout:
            self.logger.warning(f'{self.user_db_info.db_id},{msg_id} _request error: connectTimeout')
            raise ValueError('NetConnectTimeout')
        except ValueError as e:
            raise e
        except Exception as e:
            self.logger.warning(f'{self.user_db_info.db_id},{msg_id} _request error: {e}')
            self.logger.warning(f'data:{data}')
            if res:
                self.logger.warning(f'res:{res}')
                self.logger.warning(f'status_code:{res.status_code}')
                self.logger.warning(f'res.text:{res.text}')
            if return_json:
                return None
            else:
                return res

    async def _ns_api_request(self, url, multiple=False) -> dict | None:
        """ns接口层操作，如ns好友列表，我的 页面"""
        # 跨线程重载token
        self.reload_tokens()
        res = ''
        msg_id = get_msg_id(self.platform, self.user_id)
        try:
            t = time.time()
            json_body = {'parameter': {}}
            s3s = self.s3s
            if not self.access_token:
                await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                success = await self.refresh_gtoken_and_bullettoken(skip_access=False)

            await s3s.f_api_clent_auth2_register()
            # 加密参数
            encrypt_request = await s3s.f_encrypt_request(api_url=url, body_data=json_body,
                                                           access_token=self.access_token)
            encrypt_json = encrypt_request.json()
            encrypt_data = encrypt_json["data"]
            body_bytes = base64.b64decode(encrypt_data)
            # 请求nxapi
            encrypt_resp = await AsHttpReq.post(url, headers=await self._head_access(self.access_token), data=body_bytes)
            # 解密响应
            decrypt_resp = await s3s.f_decrypt_response(encrypt_resp.content)
            decrypt_data = decrypt_resp.json()["data"]
            decrypt_json = json.loads(decrypt_data)
            # self.logger.info(f'decrypt_json:{json.dumps(decrypt_json)}')
            # self.logger.info(f"ns请求res为{decrypt_resp.text}")

            t2 = f'{time.time() - t:.3f}'
            self.logger.debug(f'_request: {t2}s')
            status = decrypt_json["status"]
            self.logger.info(f"ns api请求satus为{status}")
            if status == 9404:
                # 更新token提醒一下用户
                if not multiple and self.bot and self.event:
                    await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                try:
                    self.logger.info(f'{self.user_db_info.db_id},{msg_id}  tokens expired,start refresh tokens soon')
                    success = await self.refresh_gtoken_and_bullettoken(skip_access=False)
                    if success:
                        self.logger.info(f'{self.user_db_info.db_id},{msg_id} refresh tokens complete，try again')
                    else:
                        self.logger.error(f'{self.user_db_info.db_id},{msg_id} refresh tokens fail, return None')
                        return None
                except Exception as e:
                    self.logger.info(f'{self.user_db_info.db_id},{msg_id} refresh tokens fail,reason:{e}')
                # 再次请求
                t = time.time()

                # 加密参数
                encrypt_request = await s3s.f_encrypt_request(api_url=url, body_data=json_body,
                                                              access_token=self.access_token)
                encrypt_json = encrypt_request.json()
                encrypt_data = encrypt_json['data']
                body_bytes = base64.b64decode(encrypt_data)
                # 请求nxapi
                encrypt_resp = await AsHttpReq.post(url, headers=await self._head_access(self.access_token),
                                                          data=body_bytes)
                # 解密响应
                decrypt_resp = await s3s.f_decrypt_response(encrypt_resp.content)
                decrypt_data = decrypt_resp.json()["data"]
                decrypt_json = json.loads(decrypt_data)

                t2 = f'{time.time() - t:.3f}'
                self.logger.debug(f'_request: {t2}s')

                status = decrypt_json["status"]
                if status == 9404:
                    return None
                else:
                    return decrypt_json
            else:
                return decrypt_json
        except httpx.ConnectError:
            self.logger.warning(f'{self.user_db_info.db_id},{msg_id} _ns_api_request error: connectError')
            raise ValueError('NetConnectError')
        except httpx.ConnectTimeout:
            self.logger.warning(f'{self.user_db_info.db_id},{msg_id} _ns_api_request error: connectTimeout')
            raise ValueError('NetConnectTimeout')
        except ValueError as e:
            raise e
        except Exception as e:
            self.logger.warning(f'{self.user_db_info.db_id},{msg_id} _ns_api_request error: {e}')
            self.logger.warning(f'url:{url}')
            self.logger.warning(f'res:{decrypt_resp.text}')
            # if res:
            #     self.logger.warning(f'res:{res}')
            #     self.logger.warning(f'res:{res.status_code}')
            #     self.logger.warning(f'res:{res.text}')
            return None

    async def get_recent_battles(self, multiple=False):
        """最近对战查询"""
        data = gen_graphql_body(translate_rid['LatestBattleHistoriesQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_last_one_battle(self, multiple=False):
        """最新一局对战id查询"""
        data = gen_graphql_body(translate_rid['PagerLatestVsDetailQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_bankara_battles(self, multiple=False):
        """蛮颓对战查询"""
        data = gen_graphql_body(translate_rid['BankaraBattleHistoriesQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_regular_battles(self, multiple=False):
        """涂地对战查询"""
        data = gen_graphql_body(translate_rid['RegularBattleHistoriesQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_event_battles(self, multiple=False):
        """活动对战查询"""
        data = gen_graphql_body(translate_rid['EventBattleHistoriesQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_x_battles(self, multiple=False):
        """x对战查询"""
        data = gen_graphql_body(translate_rid['XBattleHistoriesQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_x_ranking(self, area: str, multiple=False):
        """x排行榜top1查询"""
        data = gen_graphql_body(translate_rid['XRankingQuery'], varname='region', varvalue=area)
        res = await self.request(data, multiple=multiple)
        return res

    async def get_x_ranking_500(self, top_id: str, multiple=False):
        """x排行榜500强查询"""
        data = gen_graphql_body(translate_rid['XRanking500Query'], varname='id', varvalue=top_id)
        res = await self.request(data, multiple=multiple)
        return res

    async def get_custom_data(self, data, multiple=False):
        """提供data数据进行自定义查询"""
        res = await self.request(data, multiple=multiple)
        return res

    async def get_test(self, multiple=False):
        """测试内容查询"""
        data = gen_graphql_body(translate_rid['TotalQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_battle_detail(self, battle_id, multiple=False):
        """指定对战id查询细节"""
        data = gen_graphql_body(translate_rid['VsHistoryDetailQuery'], "vsResultId", battle_id)
        res = await self.request(data, multiple=multiple)
        return res

    async def get_coops(self, multiple=False):
        """打工历史"""
        data = gen_graphql_body(translate_rid['CoopHistoryQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_coop_detail(self, battle_id, multiple=False):
        """指定打工id查询细节"""
        data = gen_graphql_body(translate_rid['CoopHistoryDetailQuery'], "coopHistoryDetailId", battle_id)
        res = await self.request(data, multiple=multiple)
        return res

    async def get_coop_statistics(self, multiple=False):
        """打工统计数据(全部boss击杀数量)"""
        data = gen_graphql_body(translate_rid['CoopStatistics'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_history_summary(self, multiple=False):
        """主页 - 历史 页面 全部分类数据"""
        data = gen_graphql_body(translate_rid['HistorySummary'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_total_query(self, multiple=False):
        """nso没有这个页面，统计比赛场数"""
        data = gen_graphql_body(translate_rid['TotalQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_event_list(self, multiple=False):
        """获取活动条目"""
        data = gen_graphql_body(translate_rid['EventListQuery'])
        res = await self.request(data, multiple=multiple)
        return res

    async def get_event_items(self, top_id, multiple=False):
        """获取活动内容"""
        data = gen_graphql_body(translate_rid['EventBoardQuery'],
                                varname='eventMatchRankingPeriodId', varvalue=top_id)
        res = await self.request(data, multiple=multiple)
        return res

    async def _head_access(self, app_access_token):
        """为含有access_token的请求拼装header"""
        coral_head = {
            'User-Agent': f'com.nintendo.znca/{await S3S.get_nsoapp_version()} (Android/12)',
            'Accept-Encoding': 'gzip',
            'Connection': 'Keep-Alive',
            'Host': 'api-lp1.znc.srv.nintendo.net',
            'X-ProductVersion': await S3S.get_nsoapp_version(),
            "Content-Type": "application/octet-stream",
            "Accept": "application/octet-stream, application/json",
            'Authorization': f"Bearer {app_access_token}",
            'X-Platform': 'Android',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }
        return coral_head

    async def get_friends(self, multiple=False):
        """获取sp3好友"""
        data = gen_graphql_body(translate_rid['FriendsList'])
        res = await self.request(data, multiple=multiple)
        return res

    async def app_ns_friend_list(self, multiple=False):
        """nso 好友列表"""
        url = "https://api-lp1.znc.srv.nintendo.net/v4/Friend/List"
        try:
            res = await self._ns_api_request(url, multiple=multiple)
        except Exception as e:
            raise e
        return res

    async def app_ns_myself(self, multiple=False):
        """nso 我的 页面
        返回ns好友码"""
        url = "https://api-lp1.znc.srv.nintendo.net/v4/User/ShowSelf"
        try:
            res = await self._ns_api_request(url, multiple=multiple)
        except Exception as e:
            raise e
        name = res['result']['name']
        my_sw_code = res['result']['links']['friendCode']['id']
        icon = res['result']['imageUri']
        return {
            'name': name,
            'code': my_sw_code,
            'icon': icon
        }

    async def close(self):
        """显式释放所有资源（核心：打破所有强引用链）"""
        # 1. 关闭req_client
        # if hasattr(self, 'req_client') and self.req_client:
        #     try:
        #         await self.req_client.close()
        #     except Exception as e:
        #         self.logger.warning(f"关闭req_client失败: {e}")
        #     self.req_client = None

        # 2. 关闭S3S（如果有close方法）
        if hasattr(self, 's3s') and self.s3s:
            try:
                self.s3s.close()
            except Exception as e:
                self.logger.warning(f"关闭S3S失败: {e}")
            self.s3s = None

        # 3. 清空所有属性（打破强引用链）
        self.bot = None
        self.event = None
        self.platform = None
        self.user_id = None
        self.user_name = None
        self.nsa_id = None
        self.ns_name = None
        self.ns_friend_code = None
        self.session_token = None
        self.user_lang = None
        self.user_country = None
        self.bullet_token = None
        self.g_token = None
        self.access_token = None
        self.nso_app_version = None
        self.dict_type = None
        self.logger = None
