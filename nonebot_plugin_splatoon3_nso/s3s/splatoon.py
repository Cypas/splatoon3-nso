import time
import uuid
import os

import httpx
from loguru import logger
from nonebot import Bot
from nonebot.internal.adapter import Event

from .utils import gen_graphql_body, translate_rid, GRAPHQL_URL
from .iksm import APP_USER_AGENT, SPLATNET3_URL, S3S, F_GEN_URL, F_GEN_URL_2
from ..data.utils import GlobalUserInfo
from ..handle.send_msg import bot_send
from ..data.data_source import dict_get_or_set_user_info, model_get_or_set_user
from ..utils import DIR_RESOURCE,  get_msg_id, get_or_init_client


class UserDBInfo:
    def __init__(self, db_id, user_name, game_name, game_sp_id):
        self.db_id = db_id
        self.user_name = user_name
        self.game_name = game_name
        self.game_sp_id = game_sp_id


class Splatoon:
    def __init__(self, bot: Bot, event: Event, user_info: GlobalUserInfo):
        self.bot = bot
        self.event = event
        self.platform = bot.adapter.get_name()
        self.user_id = event.get_user_id()
        self.user_name = user_info.user_name
        self.session_token = user_info.session_token
        self.user_lang = 'zh-CN'
        self.user_country = 'JP'
        self.bullet_token = ''
        self.g_token = ''
        self.access_token = ''
        s3s = S3S(self.platform, self.user_id)
        self.s3s = s3s
        self.nso_app_version = s3s.get_nsoapp_version()
        self.req_client = user_info.req_client or get_or_init_client(self.platform, self.user_id)

        user = model_get_or_set_user(self.platform, self.user_id)
        if user:
            self.bullet_token = user.bullet_token
            self.g_token = user.g_token
            self.access_token = user.access_token
            self.user_db_info = UserDBInfo(str(user.id) or "0",
                                           user.user_name or "no user name",
                                           user.game_name or "no game name",
                                           user.game_sp_id or "")

    def set_user_info(self, **kwargs):
        """修改user信息"""
        # 修改自身类的值
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        # 修改全局字典
        dict_get_or_set_user_info(self.platform, self.user_id, **kwargs)

    async def refresh_gtoken_and_bullettoken(self):
        """刷新gtoken 和 bullettoken"""
        new_access_token, new_g_token, new_bullet_token, user_lang, user_country = \
            "", "", "", self.user_lang, self.user_country
        try:
            # user_nickname为任天堂官网账号用户名，没有参考价值
            new_access_token, new_g_token, user_nickname, user_lang, user_country = \
                await self.s3s.get_gtoken(self.session_token)
        except Exception as e:
            msg_id = get_msg_id(self.platform, self.user_id)
            logger.warning(f'{msg_id} refresh_gtoken_and_bullettoken error. {e} {self.session_token}')
            if self.user_db_info:
                user = self.user_db_info
                if 'invalid_grant' in str(e):
                    # 无效登录凭证
                    logger.warning(
                        f'invalid_grant_user: db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}')
                    self.set_user_info(session_token=None)
                    # 写入待发送文本
                    msg = f'喷3账号 {user.game_name or ""} 登录过期，请重新登录 /login \n'

                    file_msg_path = os.path.join(f'{DIR_RESOURCE}/user_msg', f'msg_{user.db_id}.txt')
                    with open(file_msg_path, 'a') as f:
                        f.write(msg)
                    return
                elif 'Membership required' in str(e):
                    # 会员过期
                    logger.warning(
                        f'membership_required: db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}')
                    _ex, nickname = str(e).split('|')
                    nickname = nickname or ''
                    logger.warning('membership_required notify')
                    # 写入待发送文本
                    msg = f'喷3账号 {nickname} 会员过期'
                    file_msg_path = os.path.join(f'{DIR_RESOURCE}/user_msg', f'msg_{user.db_id}.txt')
                    with open(file_msg_path, 'w') as f:
                        f.write(msg)
                    return
                logger.warning(
                    f'invalid_user: db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}')
                logger.warning('try f_gen_url_2 url')
                try:
                    self.s3s.f_gen_url = F_GEN_URL_2
                    new_access_token, new_g_token, user_nickname, user_lang, user_country = \
                        await self.s3s.get_gtoken(self.session_token)
                except Exception as e:
                    logger.warning(
                        f'f_gen_url_2 url also fail:{e} db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}')

        try:
            # 获取bullettoken
            new_bullet_token = await self.s3s.get_bullet(self.user_db_info.db_id, new_g_token)
        except Exception as e:
            msg_id = get_msg_id(self.platform, self.user_id)
            logger.warning(f'{msg_id} get g_token success,get bullet_token error,start try again.reason:{e}')
            new_bullet_token = await self.s3s.get_bullet(self.user_db_info.db_id, new_g_token)
        # 刷新值1
        if new_g_token and new_bullet_token:
            self.set_user_info(access_token=new_access_token, g_token=new_g_token, bullet_token=new_bullet_token)
            logger.info(f'{self.user_id} tokens updated.')
            logger.debug(f'new access_token: {new_access_token}')
            logger.debug(f'new g_token: {new_g_token}')
            logger.debug(f'new bullet_token: {new_bullet_token}')
        return True

    def _head_bullet(self, bullet_token):
        """为含有bullet_token的请求拼装header"""
        graphql_head = {
            'Authorization': f'Bearer {bullet_token}',
            'Accept-Language': self.user_lang,
            'User-Agent': APP_USER_AGENT,
            'X-Web-View-Ver': S3S.get_web_view_ver(),
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Origin': SPLATNET3_URL,
            'X-Requested-With': 'com.nintendo.znca',
            'Referer': f'{SPLATNET3_URL}/?lang={self.user_lang}&na_country={self.user_country}&na_lang={self.user_lang}',
            'Accept-Encoding': 'gzip, deflate'
        }
        return graphql_head

    async def test_page(self, try_again=False):
        """主页(测试访问页面)"""
        data = gen_graphql_body(translate_rid["HomeQuery"])
        # t = time.time()
        headers = self._head_bullet(self.bullet_token)
        cookies = dict(_gtoken=self.g_token)
        test = await self.req_client.post(GRAPHQL_URL, data=data, headers=headers, cookies=cookies)

        if test.status_code != 200:
            if test.status_code == 401:
                # 更新token提醒一下用户
                if not try_again:
                    await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                try:
                    logger.info(f'{self.user_id} tokens expired,start refresh tokens soon')
                    await self.refresh_gtoken_and_bullettoken()
                    logger.info(f'refresh tokens complete，try again')
                except Exception as e:
                    logger.info(f'refresh tokens fail,reason:{e}')
                t = time.time()
                test = await self.req_client.post(GRAPHQL_URL, data=data, headers=headers, cookies=cookies)
                t2 = f'{time.time() - t:.3f}'
                logger.debug(f'_request: {t2}s')

    async def _request(self, data, try_again=False):
        res = ''
        try:
            if not self.bullet_token or not self.g_token:
                # 首次请求如果为空时
                logger.info(f'{self.user_id} tokens is None,start refresh tokens soon')
                await self.refresh_gtoken_and_bullettoken()
                logger.debug(f'refresh tokens complete')
            t = time.time()
            res = await self.req_client.post(GRAPHQL_URL, data=data,
                                             headers=self._head_bullet(self.bullet_token),
                                             cookies=dict(_gtoken=self.g_token))
            t2 = f'{time.time() - t:.3f}'
            logger.debug(f'_request: {t2}s')
            if res.status_code != 200:
                if res.status_code == 401:
                    # 更新token提醒一下用户
                    if not try_again:
                        await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                    try:
                        logger.info(f'{self.user_id} tokens expired,start refresh tokens soon')
                        await self.refresh_gtoken_and_bullettoken()
                        logger.info(f'refresh tokens complete，try again')
                    except Exception as e:
                        logger.info(f'refresh tokens fail,reason:{e}')
                    t = time.time()
                    res = await self.req_client.post(GRAPHQL_URL, data=data,
                                                     headers=self._head_bullet(self.bullet_token),
                                                     cookies=dict(_gtoken=self.g_token))
                    t2 = f'{time.time() - t:.3f}'
                    logger.debug(f'_request: {t2}s')
                    return res.json()
            else:
                return res.json()
        except (httpx.ConnectError, httpx.ConnectTimeout):
            logger.warning(f'_request error: connectError or connect timeout')
        except Exception as e:
            logger.warning(f'_request error: {e}')
            logger.warning(f'data:{data}')
            logger.warning(f'res:{res}')
            # if res:
            #     logger.warning(f'res:{res}')
            #     logger.warning(f'res:{res.status_code}')
            #     logger.warning(f'res:{res.text}')
            return None

    async def _ns_api_request(self, url, try_again=False):
        """ns接口层操作，如ns好友列表，我的 页面"""
        app_access_token = self.access_token
        headers = self._head_access(app_access_token)
        json_body = {'parameter': {}, 'requestId': str(uuid.uuid4())}

        res = ''
        try:
            t = time.time()
            res = await self.req_client.post(url, headers=headers, json=json_body)
            t2 = f'{time.time() - t:.3f}'
            logger.debug(f'_request: {t2}s')
            if res.status_code != 200:
                if res.status_code == 401:
                    # 更新token提醒一下用户
                    if not try_again:
                        await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                    try:
                        logger.info(f'{self.user_id} tokens expired,start refresh tokens soon')
                        await self.refresh_gtoken_and_bullettoken()
                        logger.info(f'refresh tokens complete，try again')
                    except Exception as e:
                        logger.info(f'refresh tokens fail,reason:{e}')
                    t = time.time()
                    res = await self.req_client.post(url, headers=headers, json=json_body)
                    t2 = f'{time.time() - t:.3f}'
                    logger.debug(f'_request: {t2}s')
                    return res.json()
            else:
                return res.json()
        except (httpx.ConnectError, httpx.ConnectTimeout):
            logger.warning(f'_request error: connectError or connect timeout')
        except Exception as e:
            logger.warning(f'_request error: {e}')
            logger.warning(f'data:{url}')
            logger.warning(f'res:{res}')
            # if res:
            #     logger.warning(f'res:{res}')
            #     logger.warning(f'res:{res.status_code}')
            #     logger.warning(f'res:{res.text}')
            return None

    async def get_recent_battles(self, try_again=False):
        """最近对战查询"""
        data = gen_graphql_body(translate_rid['LatestBattleHistoriesQuery'])
        res = await self._request(data, try_again=try_again)
        return res

    async def get_last_one_battle(self, try_again=False):
        """最新一局对战id查询"""
        data = gen_graphql_body(translate_rid['PagerLatestVsDetailQuery'])
        res = await self._request(data, try_again=try_again)
        return res

    async def get_bankara_battles(self, try_again=False):
        """蛮颓对战查询"""
        data = gen_graphql_body(translate_rid['BankaraBattleHistoriesQuery'])
        res = await self._request(data, try_again=try_again)
        return res

    async def get_x_battles(self, try_again=False):
        """x对战查询"""
        data = gen_graphql_body(translate_rid['XBattleHistoriesQuery'])
        res = await self._request(data, try_again=try_again)
        return res

    async def get_test(self, try_again=False):
        """测试内容查询"""
        data = gen_graphql_body(translate_rid['CoopStatistics'])
        res = await self._request(data, try_again=try_again)
        return res

    async def get_battle_detail(self, battle_id, try_again=False):
        """指定对战id查询细节"""
        data = gen_graphql_body(translate_rid['VsHistoryDetailQuery'], "vsResultId", battle_id)
        res = await self._request(data, try_again=try_again)
        return res

    async def get_coops(self, try_again=False):
        """打工历史"""
        data = gen_graphql_body(translate_rid['CoopHistoryQuery'])
        res = await self._request(data, try_again=try_again)
        return res

    async def get_coop_detail(self, battle_id, try_again=False):
        """指定打工id查询细节"""
        data = gen_graphql_body(translate_rid['CoopHistoryDetailQuery'], "coopHistoryDetailId", battle_id)
        res = await self._request(data, try_again=try_again)
        return res

    async def get_coop_statistics(self, try_again=False):
        """打工统计数据(全部boss击杀数量)"""
        data = gen_graphql_body(translate_rid['CoopStatistics'])
        res = await self._request(data, try_again=try_again)
        return res

    async def get_summary(self, try_again=False):
        """"""
        data = gen_graphql_body(translate_rid['HistorySummary'])
        res = await self._request(data, try_again=try_again)
        return res

    async def get_all_res(self, try_again=False):
        """"""
        data = gen_graphql_body(translate_rid['TotalQuery'])
        res = await self._request(data, try_again=try_again)
        return res

    def app_get_access_token(self, try_again=False):
        """get nso_access_token"""
        return self.access_token

    def _head_access(self, app_access_token):
        """为含有access_token的请求拼装header"""
        graphql_head = {
            'User-Agent': f'com.nintendo.znca/{self.nso_app_version} (Android/7.1.2)',
            'Accept-Encoding': 'gzip',
            'Accept': 'application/json',
            'Connection': 'Keep-Alive',
            'Host': 'api-lp1.znc.srv.nintendo.net',
            'X-ProductVersion': self.nso_app_version,
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': f"Bearer {app_access_token}", 'X-Platform': 'Android'
        }
        return graphql_head

    async def app_ns_friend_list(self, try_again=False):
        """nso 好友列表"""
        url = "https://api-lp1.znc.srv.nintendo.net/v3/Friend/List"
        res = await self._ns_api_request(url, try_again=try_again)
        if not res:
            raise ValueError('NetConnectError')
        return res

    async def app_ns_myself(self, try_again=False):
        """nso 我的 页面
        返回ns好友码"""
        url = "https://api-lp1.znc.srv.nintendo.net/v3/User/ShowSelf"
        res = await self._ns_api_request(url, try_again=try_again)
        if not res:
            raise ValueError('NetConnectError')

        name = res['result']['name']
        my_sw_code = res['result']['links']['friendCode']['id']
        return {
            'name': name,
            'code': my_sw_code
        }

    # def app_get_token(self):
    #     """get token，与iksm函数定义重复"""
    #     headers = {
    #         'Host': 'accounts.nintendo.com',
    #         'Accept-Encoding': 'gzip',
    #         'Content-Type': 'application/json; charset=utf-8',
    #         'Accept-Language': 'en-US',
    #         'Accept': 'application/json',
    #         'Connection': 'Keep-Alive',
    #         'User-Agent': f'OnlineLounge/{self.nso_app_version} NASDKAPI Android'
    #     }
    #
    #     json_body = {
    #         'client_id': '71b963c1b7b6d119',
    #         'session_token': self.session_token,
    #         'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer-session-token'
    #     }
    #
    #     r = self.app_do_req(method='POST', url='https://accounts.nintendo.com/connect/1.0.0/api/token',
    #                         headers=headers, json=json_body)
    #     return r
    #
    # async def app_get_nintendo_account_data(self, access_token):
    #     """get user info 与iksm函数定义重复"""
    #     url = 'https://api.accounts.nintendo.com/2.0.0/users/me'
    #     headers = {
    #         "User-Agent": "OnlineLounge/2.2.0 NASDKAPI Android",
    #         "Authorization": "Bearer {}".format(access_token)
    #     }
    #     r = self.app_do_req(method='GET', url=url, headers=headers)
    #     return r
    #
    # def app_login_switch_web(self, id_token, nintendo_profile):
    #     """get access token与web service token  与iksm函数定义重复"""
    #     user_id = nintendo_profile['id']
    #     nso_f, request_id, timestamp = call_f_api(id_token, 1, F_GEN_URL, user_id)
    #
    #     headers = {
    #         'Host': 'api-lp1.znc.srv.nintendo.net',
    #         'Accept-Language': 'en-US',
    #         'User-Agent': f'com.nintendo.znca/{self.nso_app_version} (Android/7.1.2)',
    #         'Accept': 'application/json',
    #         'X-ProductVersion': self.nso_app_version,
    #         'Content-Type': 'application/json; charset=utf-8',
    #         'Connection': 'Keep-Alive',
    #         'Authorization': 'Bearer',
    #         'X-Platform': 'Android',
    #         'Accept-Encoding': 'gzip'
    #     }
    #
    #     jsonbody = {'parameter': {}}
    #     jsonbody['parameter']['f'] = nso_f
    #     jsonbody['parameter']['naIdToken'] = id_token
    #     jsonbody['parameter']['timestamp'] = timestamp
    #     jsonbody['parameter']['requestId'] = request_id
    #     jsonbody['parameter']['naCountry'] = nintendo_profile['country']
    #     jsonbody['parameter']['naBirthday'] = nintendo_profile['birthday']
    #     jsonbody['parameter']['language'] = nintendo_profile['language']
    #
    #     url = "https://api-lp1.znc.srv.nintendo.net/v3/Account/Login"
    #     r = self.app_do_req(method='POST', url=url, headers=headers, json=jsonbody)
    #     try:
    #         web_token = r["result"]["webApiServerCredential"]["accessToken"]
    #     except:
    #         logger.info(r)
    #         web_token = ''
    #     return web_token
