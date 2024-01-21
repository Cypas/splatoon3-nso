import time
import uuid
import os

from loguru import logger

from .utils import gen_graphql_body, translate_rid, GRAPHQL_URL
from .iksm import APP_USER_AGENT, SPLATNET3_URL, S3S, F_GEN_URL, F_GEN_URL_2
from ..data.data_source import dict_get_or_set_user_info, model_get_or_set_user
from ..utils import DIR_RESOURCE, HttpReq, get_msg_id, get_or_init_client


class UserDBInfo:
    def __init__(self, db_id, user_name, game_name, game_sp_id):
        self.db_id = db_id
        self.user_name = user_name
        self.game_name = game_name
        self.game_sp_id = game_sp_id


class Splatoon:
    def __init__(self, platform, user_id, user_name, session_token, req_client):
        self.platform = platform
        self.user_id = user_id
        self.user_name = user_name
        self.session_token = session_token
        self.user_lang = 'zh-CN'
        self.user_country = 'JP'
        self.bullet_token = ''
        self.g_token = ''
        self.access_token = ''
        s3s = S3S(platform, user_id)
        self.s3s = s3s
        self.nso_app_version = s3s.get_nsoapp_version()
        self.req_client = req_client or get_or_init_client(platform, user_id)

        user = model_get_or_set_user(platform, user_id)
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

    async def test_page(self):
        """主页(测试访问页面)"""
        data = gen_graphql_body(translate_rid["HomeQuery"])
        # t = time.time()
        headers = self._head_bullet(self.bullet_token)
        cookies = dict(_gtoken=self.g_token)
        test = HttpReq.post(GRAPHQL_URL, data=data, headers=headers, cookies=cookies)

        if test.status_code != 200:
            logger.info(f'{self.user_id} tokens expired.')
            await self.refresh_gtoken_and_bullettoken()

    async def _request(self, data):
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
            t2 = f'{time.time()  - t:.3f}'
            logger.debug(f'_request: {t2}s')
            if res.status_code != 200:
                logger.info(f'{self.user_id} tokens expired,start refresh tokens soon')
                if res.status_code == 401:
                    try:
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
        except Exception as e:
            logger.warning(f'api:{GRAPHQL_URL}')
            logger.warning(f'data:{data}')
            logger.warning(f'res:{res}')
            if res:
                logger.warning(f'res:{res.status_code}')
                logger.warning(f'res:{res.text}')
            logger.warning(f'_request error: {e}')
            return None

    async def get_recent_battles(self):
        """最近对战查询"""
        data = gen_graphql_body(translate_rid['LatestBattleHistoriesQuery'])
        res = await self._request(data)
        return res

    async def get_last_one_battle(self):
        """最新一局对战id查询"""
        data = gen_graphql_body(translate_rid['PagerLatestVsDetailQuery'])
        res = await self._request(data)
        return res

    async def get_bankara_battles(self):
        """蛮颓对战查询"""
        data = gen_graphql_body(translate_rid['BankaraBattleHistoriesQuery'])
        res = await self._request(data)
        return res

    async def get_x_battles(self):
        """x对战查询"""
        data = gen_graphql_body(translate_rid['XBattleHistoriesQuery'])
        res = await self._request(data)
        return res

    async def get_test(self):
        """测试内容查询"""
        data = gen_graphql_body(translate_rid['CoopStatistics'])
        res = await self._request(data)
        return res

    async def get_battle_detail(self, battle_id):
        """指定对战id查询细节"""
        data = gen_graphql_body(translate_rid['VsHistoryDetailQuery'], "vsResultId", battle_id)
        res = await self._request(data)
        return res

    async def get_coops(self):
        """打工历史"""
        data = gen_graphql_body(translate_rid['CoopHistoryQuery'])
        res = await self._request(data)
        return res

    async def get_coop_detail(self, battle_id):
        """指定打工id查询细节"""
        data = gen_graphql_body(translate_rid['CoopHistoryDetailQuery'], "coopHistoryDetailId", battle_id)
        res = await self._request(data)
        return res

    async def get_coop_statistics(self):
        """打工统计数据(全部boss击杀数量)"""
        data = gen_graphql_body(translate_rid['CoopStatistics'])
        res = await self._request(data)
        return res


    async def get_summary(self):
        """"""
        data = gen_graphql_body(translate_rid['HistorySummary'])
        res = await self._request(data)
        return res

    async def get_all_res(self):
        """"""
        data = gen_graphql_body(translate_rid['TotalQuery'])
        res = await self._request(data)
        return res

    def app_get_access_token(self):
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

    async def app_ns_friend_list(self):
        """nso 好友列表"""
        app_access_token = self.app_get_access_token()
        if not app_access_token:
            return

        headers = self._head_access(app_access_token)
        json_body = {'parameter': {}, 'requestId': str(uuid.uuid4())}
        url = "https://api-lp1.znc.srv.nintendo.net/v3/Friend/List"

        r = await self.req_client.post(url, headers=headers, json=json_body)
        return r

    async def app_ns_myself(self):
        """nso 我的 页面
        返回ns好友码"""
        app_access_token = self.app_get_access_token()
        if not app_access_token:
            return

        headers = self._head_access(app_access_token)
        json_body = {'parameter': {}, 'requestId': str(uuid.uuid4())}
        url = "https://api-lp1.znc.srv.nintendo.net/v3/User/ShowSelf"

        r = await self.req_client.post(url, headers=headers, json=json_body)
        logger.debug(r)
        name = r['result']['name']
        my_sw_code = r['result']['links']['friendCode']['id']
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
