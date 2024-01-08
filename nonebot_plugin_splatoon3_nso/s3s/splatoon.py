import time
import uuid

from loguru import logger

from .utils import gen_graphql_body, translate_rid, GRAPHQL_URL
from .iksm import get_gtoken, get_bullet, APP_USER_AGENT, SPLATNET3_URL, get_web_view_ver, get_nsoapp_version, \
    call_f_api
from ..utils import ClientReq

F_GEN_URL = 'https://api.imink.app/f'
F_GEN_URL_2 = 'https://nxapi-znca-api.fancy.org.uk/api/znca/f'


class Splatoon:
    def __init__(self, user_id, session_token):
        self.user_id = user_id
        self.old_user_id = user_id
        self.session_token = session_token
        self.user_lang = 'zh-CN'
        self.user_country = 'JP'
        self.bullet_token = ''
        self.gtoken = ''
        self.nso_app_version = get_nsoapp_version()
        user = get_or_set_user(user_id=self.user_id)
        self.user = user

        if user:
            self.user_id = user.user_id_qq or user.user_id_tg or user.user_id_wx or user.user_id_kk or user.id
            self.old_user_id = user_id
            self.bullet_token = user.bullettoken
            self.gtoken = user.gtoken
            self.user_lang = self.user_lang

    async def set_gtoken_and_bullettoken(self):
        try:
            new_gtoken, user_nickname, user_lang, user_country, _user_info = \
                await get_gtoken(F_GEN_URL, self.session_token)
        except Exception as e:
            logger.warning(f'{self.user_id} set_gtoken_and_bullettoken error. {e}\n{self.session_token}')
            if self.user:
                logger.warning(f'invalid_user: {self.user.id}, {self.user.username}, {self.user.nickname}')
            if self.user and 'invalid_grant' in str(e):
                logger.warning(f'invalid_grant_user: {self.user.id}, {self.user.username}, {self.user.nickname}')
                get_or_set_user(user_id=self.user.id, session_token=None)

                msg = f'喷喷账号{self.user.nickname or ""}登录过期，请重新登录 /login \n'
                from ..utils import DIR_RESOURCE, os
                file_msg_path = os.path.join(f'{DIR_RESOURCE}/user_msg', f'msg_{self.user.id}.txt')
                with open(file_msg_path, 'a') as f:
                    f.write(msg)
                return
            elif self.user and 'Membership required' in str(e):
                logger.warning(f'membership_required: {self.user.id}, {self.user.username}, {self.user.nickname}')
                _ex, nickname = str(e).split('|')
                nickname = nickname or ''
                logger.warning('membership_required notify')
                msg = f'喷喷账号 {nickname} 会员过期'
                from ..utils import DIR_RESOURCE, os
                file_msg_path = os.path.join(f'{DIR_RESOURCE}/user_msg', f'msg_{self.user.id}.txt')
                with open(file_msg_path, 'w') as f:
                    f.write(msg)
                return

            logger.warning('try another url')
            new_gtoken, user_nickname, user_lang, user_country, _user_info = \
                await get_gtoken(F_GEN_URL_2, self.session_token)

        new_bullettoken = await get_bullet(self.user.id, new_gtoken, user_lang, user_country)
        self.gtoken = new_gtoken
        self.bullet_token = new_bullettoken
        logger.info(f'{self.user_id} tokens updated.')
        logger.debug(f'new gtoken: {new_gtoken}')
        logger.debug(f'new bullettoken: {new_bullettoken}')
        get_or_set_user(user_id=self.old_user_id, gtoken=new_gtoken, bullettoken=new_bullettoken)
        return True

    def head_bullet(self, bullet_token):
        """为含有bullet_token的请求拼装header"""
        graphql_head = {
            'Authorization': f'Bearer {bullet_token}',
            'Accept-Language': self.user_lang,
            'User-Agent': APP_USER_AGENT,
            'X-Web-View-Ver': get_web_view_ver(),
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
        test = await ClientReq.post(GRAPHQL_URL, data=data,
                                    headers=self.head_bullet(self.bullet_token), cookies=dict(_gtoken=self.gtoken))
        # logger.debug(f'_test_page: {time.time() - t:.3f}s')
        if test.status_code != 200:
            logger.info(f'{self.user_id} tokens expired.')
            await self.set_gtoken_and_bullettoken()

    async def _request(self, data, skip_check_token=False):
        res = ''
        try:
            if not skip_check_token:
                await self.test_page()
            t = time.time()
            res = await ClientReq.post(GRAPHQL_URL, data=data,
                                       headers=self.head_bullet(self.bullet_token), cookies=dict(_gtoken=self.gtoken))
            logger.debug(f'_request: {time.time() - t:.3f}s')
            if res.status_code != 200:
                logger.info(f'{self.user_id} tokens expired.')
                await self.set_gtoken_and_bullettoken()
            else:
                return res.json()
        except Exception as e:
            logger.warning(GRAPHQL_URL)
            logger.warning(data)
            logger.warning(res)
            if res:
                logger.warning(res.status_code)
                logger.warning(res.text)
            logger.warning(f'_request error: {e}')
            return None

    async def get_recent_battles(self, skip_check_token=False):
        """最新对战查询"""
        data = gen_graphql_body(translate_rid['LatestBattleHistoriesQuery'])
        res = await self._request(data, skip_check_token)
        return res

    async def get_battle_detail(self, battle_id, skip_check_token=True):
        """指定对战id查询细节"""
        data = gen_graphql_body(translate_rid['VsHistoryDetailQuery'], "vsResultId", battle_id)
        res = await self._request(data, skip_check_token)
        return res

    async def get_coops(self, skip_check_token=True):
        """打工历史"""
        data = gen_graphql_body(translate_rid['CoopHistoryQuery'])
        res = await self._request(data, skip_check_token)
        return res

    async def get_coop_detail(self, battle_id, skip_check_token=True):
        """指定打工id查询细节"""
        data = gen_graphql_body(translate_rid['CoopHistoryDetailQuery'], "coopHistoryDetailId", battle_id)
        res = await self._request(data, skip_check_token)
        return res

    async def get_summary(self, skip_check_token=False):
        """个人历史总览"""
        data = gen_graphql_body(translate_rid['HistorySummary'])
        res = await self._request(data, skip_check_token)
        return res

    async def get_all_res(self, skip_check_token=True):
        """打工记录总览"""
        data = gen_graphql_body(translate_rid['TotalQuery'])
        res = await self._request(data, skip_check_token)
        return res

    # async def get_coop_summary(self, skip_check_token=True):
    #     """打工历史 与get_coops函数重复"""
    #     data = gen_graphql_body(translate_rid['CoopHistoryQuery'])
    #     res = await self._request(data, skip_check_token)
    #     return res

    @staticmethod
    async def app_do_req(method='POST', url='', headers=None, json=None):
        t = time.time()
        if method == 'POST':
            res = ClientReq.post(url, headers=headers, json=json)
        elif method == 'GET':
            res = ClientReq.get(url, headers=headers, json=json)
        ret = res.json()
        logger.debug(f">> {time.time() - t:.3f}s {method} {url}")
        return ret

    async def app_get_access_token(self):
        """get nso_access_token"""
        app_access_token = await get_gtoken(F_GEN_URL, self.session_token, only_nso_access_token=True)
        return app_access_token

    def head_access(self, app_access_token):
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
        app_access_token = await self.app_get_access_token()
        if not app_access_token:
            return

        headers = self.head_access(app_access_token)
        json_body = {'parameter': {}, 'requestId': str(uuid.uuid4())}
        url = "https://api-lp1.znc.srv.nintendo.net/v3/Friend/List"

        r = self.app_do_req(method='POST', url=url, headers=headers, json=json_body)
        return r

    async def app_ns_myself(self):
        """nso 我的 页面
        返回ns好友码"""
        app_access_token = await self.app_get_access_token()
        if not app_access_token:
            return

        headers = self.head_access(app_access_token)
        json_body = {'parameter': {}, 'requestId': str(uuid.uuid4())}
        url = "https://api-lp1.znc.srv.nintendo.net/v3/User/ShowSelf"

        r = self.app_do_req(method='POST', url=url, headers=headers, json=json_body)
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
