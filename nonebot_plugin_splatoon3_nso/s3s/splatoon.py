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
    global_user_info_dict, global_cron_user_info_dict
from ..utils import get_msg_id, get_or_init_client


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
        self.session_token = user_info.session_token
        self.user_lang = "zh-CN"
        self.user_country = "JP"
        self.bullet_token = ""
        self.g_token = ""
        self.access_token = ""
        s3s = S3S(self.platform, self.user_id, _type=_type)
        self.s3s = s3s
        self.nso_app_version = s3s.get_nsoapp_version()
        self.dict_type = _type
        self.req_client = user_info.req_client or get_or_init_client(self.platform, self.user_id, _type=_type)
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

    def set_user_info(self, **kwargs):
        """修改user信息"""
        # 修改自身类的值
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        # 修改全局字典
        dict_get_or_set_user_info(self.platform, self.user_id, _type=self.dict_type, **kwargs)

    async def refresh_gtoken_and_bullettoken(self):
        """刷新gtoken 和 bullettoken"""
        msg_id = get_msg_id(self.platform, self.user_id)
        new_access_token, new_g_token, new_bullet_token, user_lang, user_country = \
            "", "", "", self.user_lang, self.user_country
        try:
            # user_nickname为任天堂官网账号用户名，没有参考价值
            new_access_token, new_g_token, user_nickname, user_lang, user_country = \
                await self.s3s.get_gtoken(self.session_token)
        except Exception as e:
            self.logger.warning(f'{msg_id} refresh_g_and_b_token error. reason:{e}')
            if self.user_db_info:
                user = self.user_db_info
                if 'invalid_grant' in str(e):
                    # 无效登录凭证
                    self.logger.warning(
                        f'invalid_grant_user: db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}')
                    self.set_user_info(session_token=None)
                    # 待发送文本
                    msg = f"喷3账号 {user.game_name or ''} 登录过期，请重新登录 /login"
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
                                    f'msg_id:{msg_id} private notice error: {e}')
                        raise ValueError('invalid_grant')
                    return
                elif "Membership required" in str(e):
                    # 会员过期
                    self.logger.warning(
                        f"membership_required: db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}")
                    # 切割 会员过期 警告信息
                    nickname = str(e).split('|')[1] or ""
                    # 待发送文本
                    msg = f"喷3账号 {nickname} 会员过期"
                    if self.bot and self.event:
                        self.logger.warning('membership_required notify')
                        # 来自用户主动请求
                        await bot_send(self.bot, self.event, msg)
                    else:
                        msg += ",无法更新日报"
                        # msg += "\n/report_notify close 关闭每日日报推送"
                        # 来自定时任务
                        # if user.report_notify:
                        #     await notify_to_private(self.platform, self.user_id, msg)

                        raise ValueError('Membership required')
                    return
                self.logger.warning(
                    f'invalid_user: db_id:{user.db_id}, msg_id:{msg_id}, game_name:{user.game_name}')
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
                self.logger.info(f'another_account {u.id},{msg_id} tokens updated.')
                # 如果存在全局缓存，也更新缓存数据
                key = get_msg_id(u.platform, u.user_id)
                user_info = global_user_info_dict.get(key)
                if user_info:
                    # 更新缓存数据
                    dict_get_or_set_user_info(u.platform, u.user_id, access_token=self.access_token,
                                              g_token=self.g_token,
                                              bullet_token=self.bullet_token, user_agreement=1)
                else:
                    # 更新数据库数据
                    model_get_or_set_user(u.platform, u.user_id, access_token=self.access_token, g_token=self.g_token,
                                          bullet_token=self.bullet_token, user_agreement=1)

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

    async def test_page(self, multiple=False):
        """主页(测试访问页面) 目前只有nso截图功能需要用到这个测试访问函数"""
        data = gen_graphql_body(translate_rid["HomeQuery"])

        msg_id = get_msg_id(self.platform, self.user_id)
        if not self.bullet_token or not self.g_token:
            # 首次请求如果为空时
            self.logger.info(f'{msg_id} tokens is None,start refresh tokens soon')
            # 更新token提醒一下用户
            if not multiple and self.bot and self.event:
                await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")

            await self.refresh_gtoken_and_bullettoken()
            self.logger.debug(f'{msg_id} refresh tokens complete')

        # t = time.time()
        headers = self._head_bullet(self.bullet_token)
        cookies = dict(_gtoken=self.g_token)
        test = await self.req_client.post(GRAPHQL_URL, data=data, headers=headers, cookies=cookies)

        if test.status_code != 200:
            if test.status_code == 401:
                # 更新token提醒一下用户
                if not multiple and self.bot and self.event:
                    await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                try:
                    self.logger.info(f'{self.user_id} tokens expired,start refresh tokens soon')
                    await self.refresh_gtoken_and_bullettoken()
                    self.logger.info(f'refresh tokens complete，try again')
                except Exception as e:
                    self.logger.info(f'refresh tokens fail,reason:{e}')

    async def _request(self, data, multiple=False):
        res = ''
        msg_id = get_msg_id(self.platform, self.user_id)
        try:
            if not self.bullet_token or not self.g_token:
                # 首次请求如果为空时
                self.logger.info(f'{msg_id} tokens is None,start refresh tokens soon')
                # 更新token提醒一下用户
                if not multiple and self.bot and self.event:
                    await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")

                await self.refresh_gtoken_and_bullettoken()
                self.logger.debug(f'{msg_id} refresh tokens complete')
            t = time.time()
            res = await self.req_client.post(GRAPHQL_URL, data=data,
                                             headers=self._head_bullet(self.bullet_token),
                                             cookies=dict(_gtoken=self.g_token))
            t2 = f'{time.time() - t:.3f}'
            self.logger.debug(f'_request: {t2}s')
            if res.status_code != 200:
                # multiple请求不再刷新token，以免重复报错
                if res.status_code == 401 and not multiple:
                    # 更新token提醒一下用户
                    if self.bot and self.event:
                        await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                    try:
                        self.logger.info(f'{msg_id} tokens expired,start refresh tokens soon')
                        await self.refresh_gtoken_and_bullettoken()
                        self.logger.info(f'{msg_id} refresh tokens complete，try again')
                    except Exception as e:
                        self.logger.info(f'{msg_id} refresh tokens fail,reason:{e}')
                    t = time.time()
                    res = await self.req_client.post(GRAPHQL_URL, data=data,
                                                     headers=self._head_bullet(self.bullet_token),
                                                     cookies=dict(_gtoken=self.g_token))
                    t2 = f'{time.time() - t:.3f}'
                    self.logger.debug(f'_request: {t2}s')
                    return res.json()
                else:
                    return None
            else:
                return res.json()
        except httpx.ConnectError:
            self.logger.warning(f'{msg_id} _request error: connectError')
            raise ValueError('NetConnectError')
        except httpx.ConnectTimeout:
            self.logger.warning(f'{msg_id} _request error: connectTimeout')
            raise ValueError('NetConnectTimeout')
        except ValueError as e:
            raise e
        except Exception as e:
            self.logger.warning(f'{msg_id} _request error: {e}')
            self.logger.warning(f'data:{data}')
            if res:
                self.logger.warning(f'res:{res}')
                self.logger.warning(f'status_code:{res.status_code}')
                self.logger.warning(f'res.text:{res.text}')
            return None

    async def _ns_api_request(self, url, multiple=False):
        """ns接口层操作，如ns好友列表，我的 页面"""
        res = ''
        msg_id = get_msg_id(self.platform, self.user_id)
        try:
            t = time.time()
            json_body = {'parameter': {}, 'requestId': str(uuid.uuid4())}
            res = await self.req_client.post(url, headers=self._head_access(self.access_token), json=json_body)
            t2 = f'{time.time() - t:.3f}'
            self.logger.debug(f'_request: {t2}s')
            status = res.json()["status"]
            if status == 9404:
                # 更新token提醒一下用户
                if not multiple and self.bot and self.event:
                    await bot_send(self.bot, self.event, "本次请求需要刷新token，请求耗时会比平时更长一些，请稍等...")
                try:
                    self.logger.info(f'{msg_id}  tokens expired,start refresh tokens soon')
                    await self.refresh_gtoken_and_bullettoken()
                    self.logger.info(f'{msg_id} refresh tokens complete，try again')
                except Exception as e:
                    self.logger.info(f'{msg_id} refresh tokens fail,reason:{e}')
                # 再次请求
                json_body = {'parameter': {}, 'requestId': str(uuid.uuid4())}
                t = time.time()
                res = await self.req_client.post(url, headers=self._head_access(self.access_token), json=json_body)
                t2 = f'{time.time() - t:.3f}'
                self.logger.debug(f'_request: {t2}s')

                status = res.json()["status"] or ""
                if status == 9404:
                    return None
                else:
                    return res.json()
            else:
                return res.json()
        except httpx.ConnectError:
            self.logger.warning(f'{msg_id} _ns_api_request error: connectError')
            raise ValueError('NetConnectError')
        except httpx.ConnectTimeout:
            self.logger.warning(f'{msg_id} _ns_api_request error: connectTimeout')
            raise ValueError('NetConnectTimeout')
        except ValueError as e:
            raise e
        except Exception as e:
            self.logger.warning(f'{msg_id} _request error: {e}')
            self.logger.warning(f'data:{url}')
            self.logger.warning(f'res:{res}')
            # if res:
            #     self.logger.warning(f'res:{res}')
            #     self.logger.warning(f'res:{res.status_code}')
            #     self.logger.warning(f'res:{res.text}')
            return None

    async def get_recent_battles(self, multiple=False):
        """最近对战查询"""
        data = gen_graphql_body(translate_rid['LatestBattleHistoriesQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_last_one_battle(self, multiple=False):
        """最新一局对战id查询"""
        data = gen_graphql_body(translate_rid['PagerLatestVsDetailQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_bankara_battles(self, multiple=False):
        """蛮颓对战查询"""
        data = gen_graphql_body(translate_rid['BankaraBattleHistoriesQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_regular_battles(self, multiple=False):
        """涂地对战查询"""
        data = gen_graphql_body(translate_rid['RegularBattleHistoriesQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_event_battles(self, multiple=False):
        """活动对战查询"""
        data = gen_graphql_body(translate_rid['EventBattleHistoriesQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_x_battles(self, multiple=False):
        """x对战查询"""
        data = gen_graphql_body(translate_rid['XBattleHistoriesQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_x_ranking(self, area: str, multiple=False):
        """x排行榜top1查询"""
        data = gen_graphql_body(translate_rid['XRankingQuery'], varname='region', varvalue=area)
        res = await self._request(data, multiple=multiple)
        return res

    async def get_x_ranking_500(self, top_id: str, multiple=False):
        """x排行榜500强查询"""
        data = gen_graphql_body(translate_rid['XRanking500Query'], varname='id', varvalue=top_id)
        res = await self._request(data, multiple=multiple)
        return res

    async def get_custom_data(self, data, multiple=False):
        """提供data数据进行自定义查询"""
        res = await self._request(data, multiple=multiple)
        return res

    async def get_test(self, multiple=False):
        """测试内容查询"""
        data = gen_graphql_body(translate_rid['TotalQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_battle_detail(self, battle_id, multiple=False):
        """指定对战id查询细节"""
        data = gen_graphql_body(translate_rid['VsHistoryDetailQuery'], "vsResultId", battle_id)
        res = await self._request(data, multiple=multiple)
        return res

    async def get_coops(self, multiple=False):
        """打工历史"""
        data = gen_graphql_body(translate_rid['CoopHistoryQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_coop_detail(self, battle_id, multiple=False):
        """指定打工id查询细节"""
        data = gen_graphql_body(translate_rid['CoopHistoryDetailQuery'], "coopHistoryDetailId", battle_id)
        res = await self._request(data, multiple=multiple)
        return res

    async def get_coop_statistics(self, multiple=False):
        """打工统计数据(全部boss击杀数量)"""
        data = gen_graphql_body(translate_rid['CoopStatistics'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_history_summary(self, multiple=False):
        """主页 - 历史 页面 全部分类数据"""
        data = gen_graphql_body(translate_rid['HistorySummary'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_total_query(self, multiple=False):
        """nso没有这个页面，统计比赛场数"""
        data = gen_graphql_body(translate_rid['TotalQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_event_list(self, multiple=False):
        """获取活动条目"""
        data = gen_graphql_body(translate_rid['EventListQuery'])
        res = await self._request(data, multiple=multiple)
        return res

    async def get_event_items(self, top_id, multiple=False):
        """获取活动内容"""
        data = gen_graphql_body(translate_rid['EventBoardQuery'],
                                varname='eventMatchRankingPeriodId', varvalue=top_id)
        res = await self._request(data, multiple=multiple)
        return res

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

    async def get_friends(self, multiple=False):
        """获取sp3好友"""
        data = gen_graphql_body(translate_rid['FriendsList'])
        res = await self._request(data, multiple=multiple)
        return res

    async def app_ns_friend_list(self, multiple=False):
        """nso 好友列表"""
        url = "https://api-lp1.znc.srv.nintendo.net/v3/Friend/List"
        res = await self._ns_api_request(url, multiple=multiple)
        if not res:
            raise ValueError('NetConnectError')
        return res

    async def app_ns_myself(self, multiple=False):
        """nso 我的 页面
        返回ns好友码"""
        url = "https://api-lp1.znc.srv.nintendo.net/v3/User/ShowSelf"
        res = await self._ns_api_request(url, multiple=multiple)
        if not res:
            raise ValueError('NetConnectError')

        name = res['result']['name']
        my_sw_code = res['result']['links']['friendCode']['id']
        return {
            'name': name,
            'code': my_sw_code
        }
