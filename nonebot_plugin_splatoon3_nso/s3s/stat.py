import asyncio
import base64
import datetime
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple

import msgpack
from nonebot import logger as nb_logger

from . import utils, iksm
from .splatoon import Splatoon
from ..utils import get_msg_id, AsHttpReq

thread_pool = ThreadPoolExecutor(max_workers=4)


class CONFIG_DATA:
    def __init__(self, f_gen, session_token, stat_key, user_lang=None, user_country=None, g_token=None,
                 bullet_token=None):
        self.stat_key = stat_key
        self.user_lang = user_lang or "zh-CN"
        self.user_country = user_country or "JP"
        self.session_token = session_token
        self.g_token = g_token
        self.bullet_token = bullet_token
        self.f_gen = f_gen

    def get_config(self) -> dict:
        return {"api_key": self.stat_key, "user_lang": self.user_lang,
                "user_country": self.user_country,
                "gtoken": self.g_token, "bullettoken": self.bullet_token,
                "session_token": self.session_token, "f_gen": self.f_gen}


class STAT:
    def __init__(self, splatoon: Splatoon, config_data: CONFIG_DATA):
        self.logger = nb_logger
        self.config_data = config_data
        self.splatoon = splatoon
        self.stat_key = config_data.stat_key
        self.battle_cnt = 0
        self.coop_cnt = 0
        self.stat_url = ""

    def close(self):
        self.logger = None
        self.config_data = None
        self.splatoon = None
        self.stat_key = None
        self.battle_cnt = 0
        self.coop_cnt = 0
        self.stat_url = ""

    @property
    def session_token(self):
        return self.splatoon.session_token

    @property
    def g_token(self):
        return self.splatoon.g_token

    @property
    def bullet_token(self):
        return self.splatoon.bullet_token

    async def start(self, skipprefetch=False) -> tuple[int, int, str, str]:
        """开始stat同步"""
        which = "both"
        err_msg = ""
        if not skipprefetch:
            # 检查token
            await self.prefetch_checks()
            skipprefetch = True
        try:
            await self.check_if_missing(which, None, None, skipprefetch)
        except Exception as e:
            err_msg = str(e)
        return self.battle_cnt, self.coop_cnt, self.stat_url, err_msg

    async def check_if_missing(self, which, isblackout, istestrun, skipprefetch):
        """Checks for unuploaded battles and uploads any that are found (-r flag)."""

        # noun = utils.set_noun(which)
        # print(f"Checking if there are previously-unuploaded {noun}...")

        urls = []
        # https://github.com/fetus-hina/stat.ink/wiki/Spl3-API:-Battle-%EF%BC%8D-Get-UUID-List-(for-s3s)
        # https://github.com/fetus-hina/stat.ink/wiki/Spl3-API:-Salmon-%EF%BC%8D-Get-UUID-List
        if which in ("both", "ink"):
            urls.append("https://stat.ink/api/v3/s3s/uuid-list?lobby=adaptive")  # max 250 entries
        else:
            urls.append(None)
        if which in ("both", "salmon"):
            urls.append("https://stat.ink/api/v3/salmon/uuid-list")
        else:
            urls.append(None)

        noun = "battles"  # first (and maybe only)
        which = "ink"
        for url in urls:
            if url is not None:
                printed = False
                auth = {'Authorization': f'Bearer {self.stat_key}'}
                resp = await AsHttpReq.get(url, headers=auth)
                try:
                    statink_uploads = json.loads(resp.text)
                except:
                    # retry once
                    resp = await AsHttpReq.get(url, headers=auth)
                    try:
                        statink_uploads = json.loads(resp.text)
                    except Exception as e:
                        raise ValueError(f"statink_uploads request error:{e},resp:{resp.text}")
                    # if utils.custom_key_exists("errors_pass_silently", self.config_data.get_config()):
                    #     print(f"Error while checking recently-uploaded {noun}. Continuing...")
                    # else:
                    #     print(f"Error while checking recently-uploaded {noun}. Is stat.ink down?")
                    #     sys.exit(1)

                # ! fetch from online
                # specific - check ALL possible battles; printout - to show tokens are being checked at program start
                splatnet_ids = await self.fetch_json(which, specific=True, numbers_only=True, printout=True,
                                                     skipprefetch=skipprefetch)

                # same as code in -i section below...
                _pool = 4
                semaphore = asyncio.Semaphore(_pool)  # 并发控制

                async def process_id(id):
                    async with semaphore:
                        await self.check_if_missing_func(
                            which, noun, id, statink_uploads, isblackout, istestrun
                        )

                # 动态提交所有任务（无需分批）
                tasks = [process_id(id) for id in reversed(splatnet_ids)]
                await asyncio.gather(*tasks)

            noun = "jobs"  # for second run through the loop
            which = "salmon"

    async def check_if_missing_func(self, which, noun, id, statink_uploads, isblackout, istestrun):
        """多线程执行函数"""
        full_id = utils.b64d(id)

        if which == "ink":
            old_battle_uuid = full_id[-36:]
            new_battle_uuid = str(uuid.uuid5(utils.S3S_NAMESPACE, full_id[-52:]))
            if new_battle_uuid in statink_uploads:
                return
            if old_battle_uuid in statink_uploads:
                if not utils.custom_key_exists("force_uploads", self.config_data.get_config()):
                    return

        elif which == "salmon":
            old_job_uuid = str(
                uuid.uuid5(utils.SALMON_NAMESPACE, full_id[-52:]))  # used to do it incorrectly
            new_job_uuid = str(uuid.uuid5(utils.SALMON_NAMESPACE, full_id))
            if new_job_uuid in statink_uploads:
                return
            if old_job_uuid in statink_uploads:  # extremely low chance of conflicts... but force upload if so
                if not utils.custom_key_exists("force_uploads", self.config_data.get_config()):
                    return

        await self.fetch_and_upload_single_result(id, noun, isblackout, istestrun)

    async def fetch_and_upload_single_result(self, hash_, noun, isblackout, istestrun):
        """Performs a GraphQL request for a single vsResultId/coopHistoryDetailId and call post_result()."""

        if noun in ("battles", "battle"):
            dict_key = "VsHistoryDetailQuery"
            dict_key2 = "vsResultId"
        else:  # noun == "jobs" or "job"
            dict_key = "CoopHistoryDetailQuery"
            dict_key2 = "coopHistoryDetailId"
        data = utils.gen_graphql_body(utils.translate_rid[dict_key], dict_key2, hash_)

        result_post = await self._request(data, multiple=True)
        try:
            result = json.loads(result_post.text)
            await self.post_result(result, False, isblackout, istestrun)  # not monitoring mode
        except json.decoder.JSONDecodeError:  # retry once, hopefully avoid a few errors
            result_post = await self._request(data, multiple=True)
            try:
                result = json.loads(result_post.text)
                await self.post_result(result, False, isblackout, istestrun)
            except json.decoder.JSONDecodeError:
                pass
                # if utils.custom_key_exists("errors_pass_silently", self.config_data.get_config()):
                #     print("Error uploading one of your battles. Continuing...")
                #     pass
                # else:
                #     print(
                #         f"(!) Error uploading one of your battles. Please try running s3s again. This may also be an error on Nintendo's end. See https://github.com/frozenpandaman/s3s/issues/189 for more info. Use the `errors_pass_silently` config key to skip this {noun} and continue running the script.")
                #     sys.exit(1)

    async def gen_new_tokens(self):
        """生成新token"""
        await self.splatoon.refresh_gtoken_and_bullettoken()

    async def prefetch_checks(self):
        """检查bullet_token是否过期，并提供刷新"""
        msg_id = get_msg_id(self.splatoon.platform, self.splatoon.user_id)
        try:
            success = await self.splatoon.test_page()
            if not success:
                raise ValueError(f"{msg_id} stat prefetch_checks error:test_page fail")
        except ValueError as e:
            # 预期错误，如无效凭证和会员过期
            raise e

    async def fetch_json(self, which, separate=False, exportall=False, specific=False, numbers_only=False,
                         printout=False,
                         skipprefetch=False):
        """Returns results JSON from SplatNet 3, including a combined dictionary for battles + SR jobs if requested."""

        # if DEBUG:
        #     print(f"* fetch_json() called with which={which}, separate={separate}, " \
        #           f"exportall={exportall}, specific={specific}, numbers_only={numbers_only}")

        # if exportall and not separate:
        #     print("* fetch_json() must be called with separate=True if using exportall.")
        #     sys.exit(1)

        if not skipprefetch:
            await self.prefetch_checks()

        ink_list, salmon_list = [], []
        parent_files = []

        queries = []
        if which in ("both", "ink"):
            if specific in (True, "regular"):
                queries.append("RegularBattleHistoriesQuery")
            if specific in (True, "anarchy"):
                queries.append("BankaraBattleHistoriesQuery")
            if specific in (True, "x"):
                queries.append("XBattleHistoriesQuery")
            if specific in (True, "challenge"):
                queries.append("EventBattleHistoriesQuery")
            if specific in (True, "private") and not utils.custom_key_exists("ignore_private",
                                                                             self.config_data.get_config()):
                queries.append("PrivateBattleHistoriesQuery")
            if not specific:  # False
                queries.append("LatestBattleHistoriesQuery")
        else:
            queries.append(None)
        if which in ("both", "salmon"):
            queries.append("CoopHistoryQuery")
        else:
            queries.append(None)

        needs_sorted = False  # https://ygdp.yale.edu/phenomena/needs-washed :D

        for sha in queries:
            if sha is not None:
                lang = "zh-CN" if sha == "CoopHistoryQuery" else None
                country = "JP" if sha == "CoopHistoryQuery" else None
                sha = utils.translate_rid[sha]
                battle_ids, job_ids = [], []

                data = utils.gen_graphql_body(sha)
                query1 = await self._request(data)
                try:
                    query1_resp = json.loads(query1.text)
                except Exception as e:
                    # retry again
                    data = utils.gen_graphql_body(sha)
                    query1 = await self._request(data)
                    try:
                        query1_resp = json.loads(query1.text)
                    except Exception as e:
                        raise ValueError(f'query1 request error:{e},status_code:{query1.status_code}resp:{query1.text}')

                    # if not query1_resp.get("data"):  # catch error
                    #     print(
                    #         "\nSomething's wrong with one of the query hashes. Ensure s3s is up-to-date, and if this message persists, please open an issue on GitHub.")
                    #     sys.exit(1)

                # ink battles - latest 50 of any type
                if "latestBattleHistories" in query1_resp["data"]:
                    for battle_group in query1_resp["data"]["latestBattleHistories"]["historyGroups"]["nodes"]:
                        for battle in battle_group["historyDetails"]["nodes"]:
                            battle_ids.append(
                                battle["id"])  # don't filter out private battles here - do that in post_result()

                # ink battles - latest 50 turf war
                elif "regularBattleHistories" in query1_resp["data"]:
                    needs_sorted = True
                    for battle_group in query1_resp["data"]["regularBattleHistories"]["historyGroups"]["nodes"]:
                        for battle in battle_group["historyDetails"]["nodes"]:
                            battle_ids.append(battle["id"])
                # ink battles - latest 50 anarchy battles
                elif "bankaraBattleHistories" in query1_resp["data"]:
                    needs_sorted = True
                    for battle_group in query1_resp["data"]["bankaraBattleHistories"]["historyGroups"]["nodes"]:
                        for battle in battle_group["historyDetails"]["nodes"]:
                            battle_ids.append(battle["id"])
                # ink battles - latest 50 x battles
                elif "xBattleHistories" in query1_resp["data"]:
                    needs_sorted = True
                    for battle_group in query1_resp["data"]["xBattleHistories"]["historyGroups"]["nodes"]:
                        for battle in battle_group["historyDetails"]["nodes"]:
                            battle_ids.append(battle["id"])
                # ink battles - latest 50 challenge battles
                elif "eventBattleHistories" in query1_resp["data"]:
                    needs_sorted = True
                    for battle_group in query1_resp["data"]["eventBattleHistories"]["historyGroups"]["nodes"]:
                        for battle in battle_group["historyDetails"]["nodes"]:
                            battle_ids.append(battle["id"])
                # ink battles - latest 50 private battles
                elif "privateBattleHistories" in query1_resp["data"] \
                        and not utils.custom_key_exists("ignore_private", self.config_data.get_config()):
                    needs_sorted = True
                    for battle_group in query1_resp["data"]["privateBattleHistories"]["historyGroups"]["nodes"]:
                        for battle in battle_group["historyDetails"]["nodes"]:
                            battle_ids.append(battle["id"])

                # salmon run jobs - latest 50
                elif "coopResult" in query1_resp["data"]:
                    for shift in query1_resp["data"]["coopResult"]["historyGroups"]["nodes"]:
                        for job in shift["historyDetails"]["nodes"]:
                            job_ids.append(job["id"])

                if numbers_only:
                    ink_list.extend(battle_ids)
                    salmon_list.extend(job_ids)
                else:  # ALL DATA - TAKES A LONG TIME
                    ink_list.extend(thread_pool.map(self.fetch_detailed_result, [True] * len(battle_ids), battle_ids))

                    salmon_list.extend(
                        thread_pool.map(self.fetch_detailed_result, [False] * len(job_ids), job_ids))

                    if needs_sorted:  # put regular/bankara/event/private in order, b/c exported in sequential chunks
                        try:
                            ink_list = [x for x in ink_list if x['data']['vsHistoryDetail'] is not None]  # just in case
                            ink_list = sorted(ink_list, key=lambda d: d['data']['vsHistoryDetail']['playedTime'])
                        except:
                            pass
                            # print("(!) Exporting without sorting results.json")
                        try:
                            salmon_list = [x for x in salmon_list if x['data']['coopHistoryDetail'] is not None]
                            salmon_list = sorted(salmon_list,
                                                 key=lambda d: d['data']['coopHistoryDetail']['playedTime'])
                        except:
                            pass
                            # print("(!) Exporting without sorting coop_results.json")
                parent_files.append(query1_resp)
            else:  # sha = None (we don't want to get the specified result type)
                pass

        if exportall:
            return parent_files, ink_list, salmon_list
        else:
            if separate:
                return ink_list, salmon_list
            else:
                combined = ink_list + salmon_list
                return combined

    async def _headbutt(self, force_lang=None, force_country=None):
        """Returns a (dynamic!) header used for GraphQL requests."""
        return await self.splatoon.head_bullet(force_lang, force_country)

    def _request(self, data, multiple=False, force_lang=None, force_country=None, return_json=False):
        """sp3 整合请求"""
        return self.splatoon.request(data, multiple, force_lang, force_country, return_json)

    async def fetch_detailed_result(self, is_vs_history, history_id):
        """Helper function for fetch_json()."""

        sha = "VsHistoryDetailQuery" if is_vs_history else "CoopHistoryDetailQuery"
        varname = "vsResultId" if is_vs_history else "coopHistoryDetailId"

        data = utils.gen_graphql_body(utils.translate_rid[sha], varname, history_id)
        query2 = await self._request(data, multiple=True)
        try:
            query2_resp = json.loads(query2.text)
        except json.JSONDecodeError as e:
            data = utils.gen_graphql_body(utils.translate_rid[sha], varname, history_id)
            query2 = await self._request(data, multiple=True)
            query2_resp = json.loads(query2.text)

        return query2_resp

    async def prepare_battle_result(self, battle: dict, ismonitoring, isblackout, overview_data=None):
        """Converts the Nintendo JSON format for a battle to the stat.ink one."""

        # https://github.com/fetus-hina/stat.ink/wiki/Spl3-API:-Battle-%EF%BC%8D-Post
        payload = {}
        battle = battle["vsHistoryDetail"]

        ## UUID ##
        ##########
        try:
            full_id = utils.b64d(battle["id"])
            payload["uuid"] = str(
                uuid.uuid5(utils.S3S_NAMESPACE, full_id[-52:]))  # input format: <YYYYMMDD>T<HHMMSS>_<uuid>
        except TypeError:
            pass
            # print(
            #     "Couldn't get the battle ID. This is likely an error on Nintendo's end; running the script again may fix it. Exiting.")
            # print('\nDebug info:')
            # print(json.dumps(battle))
            # sys.exit(1)

        ## MODE ##
        ##########
        mode = battle["vsMode"]["mode"]
        if mode == "REGULAR":
            payload["lobby"] = "regular"
        elif mode == "BANKARA":
            if battle["bankaraMatch"]["mode"] == "OPEN":
                payload["lobby"] = "bankara_open"
            elif battle["bankaraMatch"]["mode"] == "CHALLENGE":
                payload["lobby"] = "bankara_challenge"
        elif mode == "PRIVATE":
            payload["lobby"] = "private"
        elif mode == "FEST":
            if utils.b64d(battle["vsMode"]["id"]) in (6, 8):  # open or tricolor
                payload["lobby"] = "splatfest_open"
            elif utils.b64d(battle["vsMode"]["id"]) == 7:
                payload["lobby"] = "splatfest_challenge"  # pro
        elif mode == "X_MATCH":
            payload["lobby"] = "xmatch"
        elif mode == "LEAGUE":  # challenge
            payload["lobby"] = "event"

        ## RULE ##
        ##########
        rule = battle["vsRule"]["rule"]
        if rule == "TURF_WAR":
            payload["rule"] = "nawabari"  # could be splatfest too
        elif rule == "AREA":
            payload["rule"] = "area"
        elif rule == "LOFT":
            payload["rule"] = "yagura"
        elif rule == "GOAL":
            payload["rule"] = "hoko"
        elif rule == "CLAM":
            payload["rule"] = "asari"
        elif rule == "TRI_COLOR":
            payload["rule"] = "tricolor"

        ## STAGE ##
        ###########
        payload["stage"] = utils.b64d(battle["vsStage"]["id"])

        ## WEAPON, K/D/A/S, PLAYER & TEAM TURF INKED ##
        ###############################################
        for i, player in enumerate(battle["myTeam"]["players"]):  # specified again in set_scoreboard()
            if player["isMyself"] == True:
                payload["weapon"] = utils.b64d(player["weapon"]["id"])
                payload["inked"] = player["paint"]
                payload["species"] = player["species"].lower()
                payload["rank_in_team"] = i + 1
                # crowns (x rank and splatfest 'dragon') set in set_scoreboard()

                if player["result"] is not None:  # null if player disconnect
                    payload["kill_or_assist"] = player["result"]["kill"]
                    payload["assist"] = player["result"]["assist"]
                    payload["kill"] = payload["kill_or_assist"] - payload["assist"]
                    payload["death"] = player["result"]["death"]
                    payload["special"] = player["result"]["special"]
                    payload["signal"] = player["result"]["noroshiTry"]  # ultra signal attempts in tricolor TW
                    break

        try:
            our_team_inked, their_team_inked = 0, 0
            for player in battle["myTeam"]["players"]:
                our_team_inked += player["paint"]
            for player in battle["otherTeams"][0]["players"]:
                their_team_inked += player["paint"]
            payload["our_team_inked"] = our_team_inked
            payload["their_team_inked"] = their_team_inked
        except:  # one of these might be able to be null? doubtful but idk lol
            pass

        ## RESULT ##
        ############
        result = battle["judgement"]
        if result == "WIN":
            payload["result"] = "win"
        elif result in ("LOSE", "DEEMED_LOSE"):
            payload["result"] = "lose"
        elif result == "EXEMPTED_LOSE":
            payload["result"] = "exempted_lose"  # doesn't count toward stats
        elif result == "DRAW":
            payload["result"] = "draw"

        ## BASIC INFO & TURF WAR ##
        ###########################
        if rule == "TURF_WAR" or rule == "TRI_COLOR":  # could be turf war
            try:
                payload["our_team_percent"] = float(battle["myTeam"]["result"]["paintRatio"]) * 100
                payload["their_team_percent"] = float(battle["otherTeams"][0]["result"]["paintRatio"]) * 100
            except:  # draw - 'result' is null
                pass
        else:  # could be a ranked mode
            try:
                payload["knockout"] = "no" if battle["knockout"] is None or battle["knockout"] == "NEITHER" else "yes"
                payload["our_team_count"] = battle["myTeam"]["result"]["score"]
                payload["their_team_count"] = battle["otherTeams"][0]["result"]["score"]
            except:  # draw - 'result' is null
                pass

        ## START/END TIMES ##
        #####################
        payload["start_at"] = utils.epoch_time(battle["playedTime"])
        payload["end_at"] = payload["start_at"] + battle["duration"]

        ## SCOREBOARD & COLOR ##
        ########################
        payload["our_team_color"] = utils.convert_color(battle["myTeam"]["color"])
        payload["their_team_color"] = utils.convert_color(battle["otherTeams"][0]["color"])

        if rule != "TRI_COLOR":
            payload["our_team_players"], payload["their_team_players"] = self.set_scoreboard(battle)
        else:
            payload["our_team_players"], payload["their_team_players"], payload[
                "third_team_players"] = self.set_scoreboard(
                battle, tricolor=True)
            payload["third_team_color"] = utils.convert_color(battle["otherTeams"][1]["color"])

        ## SPLATFEST ##
        ###############
        if mode == "FEST":
            # paint %ages set in 'basic info'
            payload["our_team_theme"] = battle["myTeam"]["festTeamName"]
            payload["their_team_theme"] = battle["otherTeams"][0]["festTeamName"]

            # NORMAL (1x), DECUPLE (10x), DRAGON (100x), DOUBLE_DRAGON (333x)
            times_battle = battle["festMatch"]["dragonMatchType"]
            if times_battle == "DECUPLE":
                payload["fest_dragon"] = "10x"
            elif times_battle == "DRAGON":
                payload["fest_dragon"] = "100x"
            elif times_battle == "DOUBLE_DRAGON":
                payload["fest_dragon"] = "333x"
            elif times_battle == "CONCH_SHELL_SCRAMBLE":
                payload["conch_clash"] = "1x"
            elif times_battle == "CONCH_SHELL_SCRAMBLE_10":
                payload["conch_clash"] = "10x"
            elif times_battle == "CONCH_SHELL_SCRAMBLE_33":  # presumed
                payload["conch_clash"] = "33x"

            payload["clout_change"] = battle["festMatch"]["contribution"]
            payload["fest_power"] = battle["festMatch"]["myFestPower"]  # pro only

        ## TRICOLOR TW ##
        #################
        if mode == "FEST" and rule == "TRI_COLOR":
            try:
                payload["third_team_percent"] = float(battle["otherTeams"][1]["result"]["paintRatio"]) * 100
            except TypeError:
                pass

            third_team_inked = 0
            for player in battle["otherTeams"][1]["players"]:
                third_team_inked += player["paint"]
            payload["third_team_inked"] = third_team_inked

            payload["third_team_theme"] = battle["otherTeams"][1]["festTeamName"]

            payload["our_team_role"] = utils.convert_tricolor_role(battle["myTeam"]["tricolorRole"])
            payload["their_team_role"] = utils.convert_tricolor_role(battle["otherTeams"][0]["tricolorRole"])
            payload["third_team_role"] = utils.convert_tricolor_role(battle["otherTeams"][1]["tricolorRole"])

        ## ANARCHY BATTLES ##
        #####################
        if mode == "BANKARA":
            # counts & knockout set in 'basic info'
            payload["rank_exp_change"] = battle["bankaraMatch"]["earnedUdemaePoint"]

            try:  # if playing in anarchy open with 2-4 people, after 5 calibration matches
                payload["bankara_power_after"] = battle["bankaraMatch"]["bankaraPower"]["power"]
            except:  # could be null in historical data
                pass

            if not payload.get("bankara_power_after"):
                try:
                    payload["series_weapon_power_after"] = battle["bankaraMatch"]["weaponPower"]
                except:  # could be null in historical data
                    pass

            battle_id = base64.b64decode(battle["id"]).decode('utf-8')
            battle_id_mutated = battle_id.replace("BANKARA", "RECENT")  # normalize the ID, make work with -M and -r

            if overview_data is None:  # no passed in file with -i
                data = utils.gen_graphql_body(utils.translate_rid["BankaraBattleHistoriesQuery"])
                overview_post = await self._request(data, multiple=True)
                try:
                    overview_data = [
                        json.loads(overview_post.text)]  # make the request in real-time in attempt to get rank, etc.
                except:
                    overview_data = None
                    # print("Failed to get recent Anarchy Battles. Proceeding without information on current rank.")
            if overview_data is not None:
                ranked_list = []
                for screen in overview_data:
                    if "bankaraBattleHistories" in screen["data"]:
                        ranked_list = screen["data"]["bankaraBattleHistories"]["historyGroups"]["nodes"]
                        break
                    elif "latestBattleHistories" in screen[
                        "data"]:  # early exports used this, and no bankaraMatchChallenge below
                        ranked_list = screen["data"]["latestBattleHistories"]["historyGroups"]["nodes"]
                        break
                for parent in ranked_list:  # groups in overview (anarchy tab) JSON/screen
                    for idx, child in enumerate(parent["historyDetails"]["nodes"]):

                        # same battle, different screens
                        overview_battle_id = base64.b64decode(child["id"]).decode('utf-8')
                        overview_battle_id_mutated = overview_battle_id.replace("BANKARA", "RECENT")

                        if overview_battle_id_mutated == battle_id_mutated:  # found the battle ID in the other file
                            full_rank = re.split('([0-9]+)', child["udemae"].lower())
                            was_s_plus_before = len(full_rank) > 1  # true if "before" rank is s+

                            payload["rank_before"] = full_rank[0]
                            if was_s_plus_before:
                                payload["rank_before_s_plus"] = int(full_rank[1])

                            # anarchy battle (series) - not open
                            if "bankaraMatchChallenge" in parent and parent["bankaraMatchChallenge"] is not None:

                                # rankedup = parent["bankaraMatchChallenge"]["isUdemaeUp"]
                                ranks = ["c-", "c", "c+", "b-", "b", "b+", "a-", "a", "a+",
                                         "s"]  # s+ handled separately

                                # rank-up battle
                                if parent["bankaraMatchChallenge"]["isPromo"] == True:
                                    payload["rank_up_battle"] = "yes"
                                else:
                                    payload["rank_up_battle"] = "no"

                                if parent["bankaraMatchChallenge"]["udemaeAfter"] is not None:
                                    if idx != 0:
                                        payload["rank_after"] = payload["rank_before"]
                                        if was_s_plus_before:  # not a rank-up battle, so must be the same
                                            payload["rank_after_s_plus"] = payload["rank_before_s_plus"]
                                    else:  # the battle where we actually ranked up
                                        full_rank_after = re.split('([0-9]+)',
                                                                   parent["bankaraMatchChallenge"][
                                                                       "udemaeAfter"].lower())
                                        payload["rank_after"] = full_rank_after[0]
                                        if len(full_rank_after) > 1:
                                            payload["rank_after_s_plus"] = int(full_rank_after[1])

                                if idx == 0:  # for the most recent battle in the series only
                                    # send overall win/lose count
                                    payload["challenge_win"] = parent["bankaraMatchChallenge"]["winCount"]
                                    payload["challenge_lose"] = parent["bankaraMatchChallenge"]["loseCount"]

                                    # send exp change (gain)
                                    if payload["rank_exp_change"] is None:
                                        payload["rank_exp_change"] = parent["bankaraMatchChallenge"][
                                            "earnedUdemaePoint"]

                                # if DEBUG:
                                #     print(f'* {battle["judgement"]} {idx}')
                                #     print(f'* rank_before: {payload["rank_before"]}')
                                #     print(f'* rank_after: {payload["rank_after"]}')
                                #     print(f'* rank up battle: {parent["bankaraMatchChallenge"]["isPromo"]}')
                                #     print(f'* is ranked up: {parent["bankaraMatchChallenge"]["isUdemaeUp"]}')
                                #     if idx == 0:
                                #         print(
                                #             f'* rank_exp_change: {parent["bankaraMatchChallenge"]["earnedUdemaePoint"]}')
                                #     else:
                                #         print(f'* rank_exp_change: 0')
                            break  # found the child ID, no need to continue

        ## X BATTLES ##
        ###############
        if mode == "X_MATCH":
            # counts & knockout set in 'basic info'
            if battle["xMatch"]["lastXPower"] is not None:
                payload["x_power_before"] = battle["xMatch"]["lastXPower"]

            battle_id = base64.b64decode(battle["id"]).decode('utf-8')
            battle_id_mutated = battle_id.replace("XMATCH", "RECENT")

            if overview_data is None:  # no passed in file with -i
                data = utils.gen_graphql_body(utils.translate_rid["XBattleHistoriesQuery"])
                overview_post = await self._request(data, multiple=True)
                try:
                    overview_data = [
                        json.loads(overview_post.text)]  # make the request in real-time in attempt to get rank, etc.
                except:
                    overview_data = None
                    # print("Failed to get recent X Battles. Proceeding without some information on X Power.")
            if overview_data is not None:
                x_list = []
                for screen in overview_data:
                    if "xBattleHistories" in screen["data"]:
                        x_list = screen["data"]["xBattleHistories"]["historyGroups"]["nodes"]
                        break
                for parent in x_list:  # groups in overview (x tab) JSON/screen
                    for idx, child in enumerate(parent["historyDetails"]["nodes"]):

                        overview_battle_id = base64.b64decode(child["id"]).decode('utf-8')
                        overview_battle_id_mutated = overview_battle_id.replace("XMATCH", "RECENT")

                        if overview_battle_id_mutated == battle_id_mutated:
                            if idx == 0:
                                # best of 5 for getting x power at season start, best of 3 after
                                payload["challenge_win"] = parent["xMatchMeasurement"]["winCount"]
                                payload["challenge_lose"] = parent["xMatchMeasurement"]["loseCount"]

                                if parent["xMatchMeasurement"]["state"] == "COMPLETED":
                                    payload["x_power_after"] = parent["xMatchMeasurement"]["xPowerAfter"]
                                break

        ## CHALLENGES ##
        ################
        if mode == "LEAGUE":
            payload["event"] = battle["leagueMatch"]["leagueMatchEvent"]["id"]  # send in Base64
            payload["event_power"] = battle["leagueMatch"]["myLeaguePower"]
        # luckily no need to look at overview screen for any info

        # to check: any ranked-specific stuff for challenges in battle.leagueMatch...?

        ## MEDALS ##
        ############
        medals = []
        for medal in battle["awards"]:
            medals.append(medal["name"])
        payload["medals"] = medals

        # no way to get: level_before/after, cash_before/after

        payload["automated"] = "yes"  # data was not manually entered!

        if isblackout:
            # fix payload
            for player in payload["our_team_players"]:
                if player["me"] == "no":  # only black out others
                    player["name"] = None
                    player["number"] = None
                    player["splashtag_title"] = None
            for player in payload["their_team_players"]:
                player["name"] = None
                player["number"] = None
                player["splashtag_title"] = None
            if "third_team_players" in payload:
                for player in payload["third_team_players"]:
                    player["name"] = None
                    player["number"] = None
                    player["splashtag_title"] = None

            # fix battle json
            for player in battle["myTeam"]["players"]:
                if not player["isMyself"]:  # only black out others
                    player["name"] = None
                    player["nameId"] = None
                    player["byname"] = None
            for team in battle["otherTeams"]:
                for player in team["players"]:
                    player["name"] = None
                    player["nameId"] = None
                    player["byname"] = None

        payload["splatnet_json"] = json.dumps(battle)

        return payload

    async def prepare_job_result(self, job, ismonitoring, isblackout, overview_data=None, prevresult=None):
        '''Converts the Nintendo JSON format for a Salmon Run job to the stat.ink one.'''

        # https://github.com/fetus-hina/stat.ink/wiki/Spl3-API:-Salmon-%EF%BC%8D-Post
        payload = {}
        job = job["coopHistoryDetail"]

        full_id = utils.b64d(job["id"])
        payload["uuid"] = str(uuid.uuid5(utils.SALMON_NAMESPACE, full_id))

        job_rule = job["rule"]
        if job_rule in ("PRIVATE_CUSTOM", "PRIVATE_SCENARIO"):
            payload["private"] = "yes"
        else:
            payload["private"] = "yes" if job["jobPoint"] is None else "no"
        is_private = True if payload["private"] == "yes" else False

        payload["big_run"] = "yes" if job_rule == "BIG_RUN" else "no"
        payload["eggstra_work"] = "yes" if job_rule == "TEAM_CONTEST" else "no"

        payload["stage"] = utils.b64d(job["coopStage"]["id"])

        if job_rule != "TEAM_CONTEST":  # not present for overall job in eggstra work
            payload["danger_rate"] = job["dangerRate"] * 100
        payload["king_smell"] = job["smellMeter"]

        waves_cleared = job["resultWave"] - 1  # resultWave = 0 if all normal waves cleared
        max_waves = 5 if job_rule == "TEAM_CONTEST" else 3
        payload["clear_waves"] = max_waves if waves_cleared == -1 else waves_cleared

        if payload["clear_waves"] < 0:  # player dc'd
            payload["clear_waves"] = None

        elif payload["clear_waves"] != max_waves:  # job failure
            last_wave = job["waveResults"][payload["clear_waves"]]
            if last_wave["teamDeliverCount"] >= last_wave["deliverNorm"]:  # delivered more than quota, but still failed
                payload["fail_reason"] = "wipe_out"

        # xtrawave only
        # https://stat.ink/api-info/boss-salmonid3
        if job["bossResult"]:
            try:
                payload["king_salmonid"] = utils.b64d(job["bossResult"]["boss"]["id"])
            except KeyError:
                pass
                # print(
                #     "Could not send unsupported King Salmonid data to stat.ink. You may want to delete & re-upload this job later.")

            payload["clear_extra"] = "yes" if job["bossResult"]["hasDefeatBoss"] else "no"

        # https://stat.ink/api-info/salmon-title3
        if not is_private and job_rule != "TEAM_CONTEST":  # only in regular, not private or eggstra work
            payload["title_after"] = utils.b64d(job["afterGrade"]["id"])
            payload["title_exp_after"] = job["afterGradePoint"]

            # never sure of points gained unless first job of rot - wave 3 clear is usu. +20, but 0 if playing w/ diff-titled friends
            if job.get("previousHistoryDetail") != None:
                prev_job_id = job["previousHistoryDetail"]["id"]

                if overview_data:  # passed in a file, so no web request needed
                    if prevresult:
                        # compare stage - if different, this is the first job of a rotation, where you start at 40
                        if job["coopStage"]["id"] != prevresult["coopHistoryDetail"]["coopStage"]["id"]:
                            payload["title_before"] = payload["title_after"]  # can't go up or down from just one job
                            payload["title_exp_before"] = 40
                        else:
                            try:
                                payload["title_before"] = utils.b64d(
                                    prevresult["coopHistoryDetail"]["afterGrade"]["id"])
                                payload["title_exp_before"] = prevresult["coopHistoryDetail"]["afterGradePoint"]
                            except KeyError:  # prev job was private or disconnect
                                pass
                else:
                    data = utils.gen_graphql_body(utils.translate_rid["CoopHistoryDetailQuery"],"coopHistoryDetailId", prev_job_id)
                    prev_job_post = await self._request(data, multiple=True)
                    try:
                        prev_job = json.loads(prev_job_post.text)

                        # do stage comparison again
                        if job["coopStage"]["id"] != prev_job["data"]["coopHistoryDetail"]["coopStage"]["id"]:
                            payload["title_before"] = payload["title_after"]
                            payload["title_exp_before"] = 40
                        else:
                            try:
                                payload["title_before"] = utils.b64d(
                                    prev_job["data"]["coopHistoryDetail"]["afterGrade"]["id"])
                                payload["title_exp_before"] = prev_job["data"]["coopHistoryDetail"]["afterGradePoint"]
                            except (KeyError,
                                    TypeError):  # private or disconnect, or the json was invalid (expired job >50 ago) or something
                                pass
                    except json.decoder.JSONDecodeError:
                        pass

        geggs = 0
        peggs = job["myResult"]["deliverCount"]
        for player in job["memberResults"]:
            peggs += player["deliverCount"]
        for wave in job["waveResults"]:
            geggs += wave["teamDeliverCount"] if wave["teamDeliverCount"] != None else 0
        payload["golden_eggs"] = geggs
        payload["power_eggs"] = peggs

        if job["scale"]:
            payload["gold_scale"] = job["scale"]["gold"]
            payload["silver_scale"] = job["scale"]["silver"]
            payload["bronze_scale"] = job["scale"]["bronze"]

        payload["job_score"] = job["jobScore"]  # job score
        payload["job_rate"] = job["jobRate"]  # pay grade
        payload["job_bonus"] = job["jobBonus"]  # clear bonus
        payload["job_point"] = job["jobPoint"]  # your points = floor((score x rate) + bonus)
        # note the current bug with "bonus" lol... https://github.com/frozenpandaman/s3s/wiki/%7C-splatnet-bugs

        # species sent in player struct

        translate_special = {  # used in players and waves below
            20006: "nicedama",
            20007: "hopsonar",
            20009: "megaphone51",
            20010: "jetpack",
            20012: "kanitank",
            20013: "sameride",
            20014: "tripletornado",
            20017: "teioika",
            20018: "ultra_chakuchi"
        }

        players = []
        players_json = [job["myResult"]]
        for teammate in job["memberResults"]:
            players_json.append(teammate)

        for i, player in enumerate(players_json):
            player_info = {}
            player_info["me"] = "yes" if i == 0 else "no"
            player_info["name"] = player["player"]["name"]
            player_info["number"] = player["player"]["nameId"]
            player_info["splashtag_title"] = player["player"]["byname"]
            player_info["golden_eggs"] = player["goldenDeliverCount"]
            player_info["golden_assist"] = player["goldenAssistCount"]
            player_info["power_eggs"] = player["deliverCount"]
            player_info["rescue"] = player["rescueCount"]
            player_info["rescued"] = player["rescuedCount"]
            player_info["defeat_boss"] = player["defeatEnemyCount"]
            player_info["species"] = player["player"]["species"].lower()

            dc_indicators = [
                player_info["golden_eggs"],
                player_info["power_eggs"],
                player_info["rescue"],
                player_info["rescued"],
                player_info["defeat_boss"]
            ]
            player_info["disconnected"] = "yes" if all(value == 0 for value in dc_indicators) else "no"

            try:
                player_info["uniform"] = utils.b64d(player["player"]["uniform"]["id"])
            except KeyError:
                pass
                # print("Could not send unsupported Salmon Run gear data to stat.ink. You may want to delete & re-upload this job later.")

            if player["specialWeapon"]:  # if null, player dc'd
                try:
                    special_id = player["specialWeapon"]["weaponId"]  # post-v2.0.0 key
                except KeyError:
                    special_id = utils.b64d(player["specialWeapon"]["id"])
                try:
                    player_info["special"] = translate_special[special_id]
                except KeyError:  # invalid special weapon - likely defaulted to '1' before it could be assigned
                    pass

            weapons = []
            gave_warning = False
            for weapon in player[
                "weapons"]:  # should always be returned in in english due to headbutt() using forcelang
                wep_string = weapon["name"].lower().replace(" ", "_").replace("-", "_").replace(".", "").replace("'",
                                                                                                                 "")
                if wep_string == "random":  # NINTENDOOOOOOO
                    wep_string = None
                else:
                    try:
                        wep_string.encode(encoding='utf-8').decode('ascii')
                    except UnicodeDecodeError:  # detect non-latin characters... not all non-english strings, but many
                        wep_string = None
                        if not gave_warning:
                            gave_warning = True
                            # print(
                            #     "(!) Proceeding without weapon names. See https://github.com/frozenpandaman/s3s/issues/95 to fix this.")

                weapons.append(wep_string)
            player_info["weapons"] = weapons

            players.append(player_info)
        payload["players"] = players

        waves = []
        for i, wave in enumerate(job["waveResults"]):
            wave_info = {}
            wave_info["tide"] = "low" if wave["waterLevel"] == 0 else "high" if wave["waterLevel"] == 2 else "normal"
            wave_info["golden_quota"] = wave["deliverNorm"]
            wave_info["golden_delivered"] = wave["teamDeliverCount"]
            wave_info["golden_appearances"] = wave["goldenPopCount"]
            if job_rule == "TEAM_CONTEST":  # waves only have indiv hazard levels in eggstra work
                if i == 0:
                    haz_level = 60
                else:
                    num_players = len(players)
                    quota = waves[-1]["golden_quota"]  # last wave, most recent one added to the list
                    delivered = waves[-1]["golden_delivered"]
                    added_percent = 0  # default, no increase if less than 1.5x quota delivered
                    if num_players == 4:
                        if delivered >= quota * 2:
                            added_percent = 60
                        elif delivered >= quota * 1.5:
                            added_percent = 30
                    elif num_players == 3:
                        if delivered >= quota * 2:
                            added_percent = 40
                        elif delivered >= quota * 1.5:
                            added_percent = 20
                    elif num_players == 2:
                        if delivered >= quota * 2:
                            added_percent = 20
                        elif delivered >= quota * 1.5:
                            added_percent = 10
                    elif num_players == 1:
                        if delivered >= quota * 2:
                            added_percent = 10
                        elif delivered >= quota * 1.5:
                            added_percent = 5

                    prev_percent = waves[-1]["danger_rate"]

                    haz_level = prev_percent + added_percent
                wave_info["danger_rate"] = haz_level

            if wave["eventWave"]:
                event_id = utils.b64d(wave["eventWave"]["id"])
                translate_occurrence = {
                    1: "rush",
                    2: "goldie_seeking",
                    3: "the_griller",
                    4: "the_mothership",
                    5: "fog",
                    6: "cohock_charge",
                    7: "giant_tornado",
                    8: "mudmouth_eruption"
                }
                wave_info["event"] = translate_occurrence[event_id]

            special_uses = {
                "nicedama": 0,
                "hopsonar": 0,
                "megaphone51": 0,
                "jetpack": 0,
                "kanitank": 0,
                "sameride": 0,
                "tripletornado": 0,
                "teioika": 0,
                "ultra_chakuchi": 0,
                "unknown": 0
            }
            for wep_use in wave["specialWeapons"]:
                special_id = utils.b64d(wep_use["id"])
                special_key = translate_special.get(special_id, "unknown")
                special_uses[special_key] += 1  # increment value of the key each time it's found
            wave_info["special_uses"] = special_uses

            waves.append(wave_info)
        payload["waves"] = waves

        # https://stat.ink/api-info/boss-salmonid3
        bosses = {}
        translate_boss = {
            4: "bakudan",
            5: "katapad",
            6: "teppan",
            7: "hebi",
            8: "tower",
            9: "mogura",
            10: "koumori",
            11: "hashira",
            12: "diver",
            13: "tekkyu",
            14: "nabebuta",
            15: "kin_shake",
            17: "grill",
            20: "doro_shake"
        }
        for boss in job["enemyResults"]:
            boss_id = utils.b64d(boss["enemy"]["id"])
            boss_key = translate_boss[boss_id]
            bosses[boss_key] = {
                "appearances": boss["popCount"],
                "defeated": boss["teamDefeatCount"],
                "defeated_by_me": boss["defeatCount"]
            }
        payload["bosses"] = bosses

        payload["start_at"] = utils.epoch_time(job["playedTime"])

        if isblackout:
            # fix payload
            for player in payload["players"]:
                if player["me"] == "no":
                    player["name"] = None
                    player["number"] = None
                    player["splashtag_title"] = None

            # fix job json
            for player in job["memberResults"]:
                player["player"]["name"] = None
                player["player"]["nameId"] = None
                player["player"]["byname"] = None

        payload["splatnet_json"] = json.dumps(job)
        payload["automated"] = "yes"

        return payload

    async def post_result(self, data, ismonitoring, isblackout, istestrun, overview_data=None):
        '''Uploads battle/job JSON to stat.ink, and prints the returned URL or error message.'''

        if isinstance(data, list):  # -o export format
            try:
                data = [x for x in data if
                        x["data"]["vsHistoryDetail"] is not None]  # avoid {"data": {"vsHistoryDetail": None}} error
                results = sorted(data, key=lambda d: d["data"]["vsHistoryDetail"]["playedTime"])
            except KeyError:
                try:
                    data = [x for x in data if x["data"]["coopHistoryDetail"] is not None]
                    results = sorted(data, key=lambda d: d["data"]["coopHistoryDetail"]["playedTime"])
                except KeyError:  # unsorted - shouldn't happen
                    # print("(!) Uploading without chronologically sorting results")
                    results = data
        elif isinstance(data, dict):
            try:
                results = data["results"]
            except KeyError:
                results = [data]  # single battle/job - make into a list

        # filter down to one battle at a time
        for i in range(len(results)):
            if "vsHistoryDetail" in results[i]["data"]:  # ink battle
                payload = await self.prepare_battle_result(results[i]["data"], ismonitoring, isblackout, overview_data)
                which = "ink"
            elif "coopHistoryDetail" in results[i]["data"]:  # salmon run job
                prevresult = results[i - 1]["data"] if i > 0 else None
                payload = await self.prepare_job_result(results[i]["data"], ismonitoring, isblackout, overview_data,
                                                        prevresult=prevresult)
                which = "salmon"
            # else:  # shouldn't happen
            #     print("Ill-formatted JSON while uploading. Exiting.")
            #     print('\nDebug info:')
            #     print(json.dumps(results))
            #     sys.exit(1)  # always exit here - something is seriously wrong

            if not payload:  # empty payload
                return

            if len(payload) == 0:  # received blank payload from prepare_job_result() - skip unsupported battle
                continue

            # should have been taken care of in fetch_json() but just in case...
            if payload.get("lobby") == "private" and utils.custom_key_exists("ignore_private",
                                                                             self.config_data.get_config()) or \
                    payload.get("private") == "yes" and utils.custom_key_exists("ignore_private_jobs",
                                                                                self.config_data.get_config()):  # SR version
                continue

            s3s_values = {'agent': f'{iksm.S3S_AGENT}', 'agent_version': f'v{iksm.S3S_VERSION}',
                          "agent_variables": {'Upload Mode': "Monitoring" if ismonitoring else "Manual"}}  # lol
            payload.update(s3s_values)

            # if payload["agent"][0:3] != os.path.basename(__file__)[:-3]:
            #     print("Could not upload. Please contact @frozenpandaman on GitHub for assistance.")
            #     sys.exit(0)

            if istestrun:
                payload["test"] = "yes"

            # POST
            url = "https://stat.ink/api/v3"
            if which == "ink":
                url += "/battle"
            elif which == "salmon":
                url += "/salmon"
            auth = {'Authorization': f'Bearer {self.stat_key}', 'Content-Type': 'application/x-msgpack'}
            postbattle = await AsHttpReq.post(url, headers=auth, data=msgpack.packb(payload),
                                                             follow_redirects=False)
            ##### allow_redirects是request的参数，httpx参数名为 follow_redirects

            # response
            headerloc = postbattle.headers.get('location')
            time_now = int(time.time())
            try:
                time_uploaded = json.loads(postbattle.text)["created_at"]["time"]
            except KeyError:
                time_uploaded = None
            except json.decoder.JSONDecodeError:  # retry once
                postbattle = await AsHttpReq.post(url, headers=auth, data=msgpack.packb(payload),
                                                                 follow_redirects=False)
                headerloc = postbattle.headers.get('location')
                time_now = int(time.time())
                try:
                    time_uploaded = json.loads(postbattle.text)["created_at"]["time"]
                except:
                    pass
                    # print("Error with stat.ink. Please try again.")

            detail_type = "vsHistoryDetail" if which == "ink" else "coopHistoryDetail"
            result_id = results[i]["data"][detail_type]["id"]
            noun = utils.set_noun(which)[:-1]

            # if DEBUG:
            #     print(f"* time uploaded: {time_uploaded}; time now: {time_now}")

            if istestrun and postbattle.status_code == 200:
                pass
                # print(f"Successfully validated {noun} ID {result_id} with stat.ink.")

            elif postbattle.status_code != 201:  # Created (or already exists)
                pass
                # print(f"Error uploading {noun}. (ID: {result_id})")
                # print("Message from server:")
                # print(postbattle.content.decode('utf-8'))

            elif time_uploaded <= time_now - 7:  # give some leeway
                pass
                # print(f"{noun.capitalize()} already uploaded - {headerloc}")

            else:  # 200 OK
                # 同步数量计数
                if noun == "battle":
                    self.battle_cnt += 1
                if noun == "job":
                    self.coop_cnt += 1
                stat_url = headerloc.split('spl3')[0].split('salmon3')[0][:-1]
                self.stat_url = stat_url
                # print(f"{noun.capitalize()} uploaded to {headerloc}")
                # eg https://stat.ink/@ricochet/spl3/e2cda397-3946-4257-864f-6e3d83055618

    # async def check_for_new_results(self, which, cached_battles, cached_jobs, battle_wins, battle_losses, battle_draws,
    #                                 splatfest_wins, splatfest_losses, splatfest_draws, mirror_matches, job_successes,
    #                                 job_failures, isblackout, istestrun):
    #     """Helper function for monitor_battles(), called every N seconds or when exiting."""
    #
    #     # ! fetch from online
    #     # check only numbers (quicker); specific=False since checks recent (latest) only
    #     try:
    #         ink_results, salmon_results = self.fetch_json(which, separate=True, numbers_only=True)
    #     except:  # e.g. JSONDecodeError - tokens have probably expired
    #         await self.gen_new_tokens()  # we don't have to do prefetch_checks(), we know they're expired. gen new ones and try again
    #         ink_results, salmon_results = self.fetch_json(which, separate=True, numbers_only=True)
    #     foundany = False
    #
    #     if which in ("both", "ink"):
    #         for num in reversed(ink_results):
    #             if num not in cached_battles:
    #                 # get the full battle data
    #                 result_post = await self.splatoon.req_client.post(utils.GRAPHQL_URL,
    #                                                                   data=utils.gen_graphql_body(
    #                                                                       utils.translate_rid["VsHistoryDetailQuery"],
    #                                                                       "vsResultId", num),
    #                                                                   headers=self._headbutt(),
    #                                                                   cookies=dict(_gtoken=self.g_token))
    #                 result = json.loads(result_post.text)
    #
    #                 if result["data"]["vsHistoryDetail"]["vsMode"]["mode"] == "PRIVATE" \
    #                         and utils.custom_key_exists("ignore_private", self.config_data.get_config()):
    #                     pass
    #                 else:
    #                     foundany = True
    #                     if result["data"]["vsHistoryDetail"]["judgement"] == "WIN":
    #                         outcome = "Victory"
    #                     elif result["data"]["vsHistoryDetail"]["judgement"] in ("LOSE", "DEEMED_LOSE", "EXEMPTED_LOSE"):
    #                         outcome = "Defeat"
    #                     else:
    #                         outcome = "Draw"
    #                     splatfest_match = True if result["data"]["vsHistoryDetail"]["vsMode"][
    #                                                   "mode"] == "FEST" else False
    #                     if splatfest_match:  # keys will exist
    #                         our_team_name = result["data"]["vsHistoryDetail"]["myTeam"]["festTeamName"]
    #                         their_team_name = result["data"]["vsHistoryDetail"]["otherTeams"][0]["festTeamName"]
    #                         # works for tricolor too, since all teams would be the same
    #                         mirror_match = True if our_team_name == their_team_name else False
    #                     if outcome == "Victory":
    #                         battle_wins += 1
    #                         if splatfest_match and not mirror_match:
    #                             splatfest_wins += 1
    #                     elif outcome == "Defeat":
    #                         battle_losses += 1
    #                         if splatfest_match and not mirror_match:
    #                             splatfest_losses += 1
    #                     else:
    #                         battle_draws += 1
    #                         if splatfest_match and not mirror_match:
    #                             splatfest_draws += 1
    #                     if splatfest_match and mirror_match:
    #                         mirror_matches += 1
    #
    #                     stagename = result["data"]["vsHistoryDetail"]["vsStage"]["name"]
    #                     shortname = stagename.split(" ")[-1]
    #                     if shortname == "d'Alfonsino":  # lol franch
    #                         shortname = "Museum"
    #                     elif shortname == "Co.":
    #                         shortname = "Cargo"
    #                     endtime = utils.epoch_time(result["data"]["vsHistoryDetail"]["playedTime"]) + \
    #                               result["data"]["vsHistoryDetail"]["duration"]
    #                     dt = datetime.datetime.fromtimestamp(endtime).strftime('%I:%M:%S %p').lstrip("0")
    #
    #                     # print(f"New battle result detected at {dt}! ({shortname}, {outcome})")
    #                 cached_battles.append(num)
    #                 await self.post_result(result, True, isblackout, istestrun)  # True = is monitoring mode
    #
    #     if which in ("both", "salmon"):
    #         for num in reversed(salmon_results):
    #             if num not in cached_jobs:
    #                 # get the full job data
    #                 result_post = await self.splatoon.req_client.post(utils.GRAPHQL_URL,
    #                                                                   data=utils.gen_graphql_body(
    #                                                                       utils.translate_rid["CoopHistoryDetailQuery"],
    #                                                                       "coopHistoryDetailId", num),
    #                                                                   headers=self._headbutt(force_lang="zh-CN",
    #                                                                                         force_country="JP"),
    #                                                                   cookies=dict(_gtoken=self.g_token))
    #                 result = json.loads(result_post.text)
    #
    #                 if result["data"]["coopHistoryDetail"]["jobPoint"] is None \
    #                         and utils.custom_key_exists("ignore_private_jobs",
    #                                                     self.config_data.get_config()):  # works pre- and post-2.0.0
    #                     pass
    #                 else:
    #                     foundany = True
    #                     outcome = "Clear" if result["data"]["coopHistoryDetail"]["resultWave"] == 0 else "Defeat"
    #                     if outcome == "Clear":
    #                         job_successes += 1
    #                     else:
    #                         job_failures += 1
    #
    #                     stagename = result["data"]["coopHistoryDetail"]["coopStage"]["name"]
    #                     shortname = stagename.split(" ")[-1]  # fine for salmon run stage names too
    #                     endtime = utils.epoch_time(result["data"]["coopHistoryDetail"]["playedTime"])
    #
    #                     dt = datetime.datetime.fromtimestamp(endtime).strftime('%I:%M:%S %p').lstrip("0")
    #                     # print(f"New job result detected at {dt}! ({shortname}, {outcome})")
    #                     cached_jobs.append(num)
    #                     await self.post_result(result, True, isblackout, istestrun)  # True = is monitoring mode
    #
    #     return which, cached_battles, cached_jobs, battle_wins, battle_losses, battle_draws, splatfest_wins, splatfest_losses, splatfest_draws, mirror_matches, job_successes, job_failures, foundany

    @staticmethod
    def populate_gear_abilities(player):
        '''Returns string representing all 12 ability slots for the player's gear, for use in set_scoreboard().'''

        h_main = utils.translate_gear_ability(player["headGear"]["primaryGearPower"]["image"]["url"])
        h_subs = []
        if len(player["headGear"]["additionalGearPowers"]) > 0:
            h_subs.append(utils.translate_gear_ability(player["headGear"]["additionalGearPowers"][0]["image"]["url"]))
        if len(player["headGear"]["additionalGearPowers"]) > 1:
            h_subs.append(utils.translate_gear_ability(player["headGear"]["additionalGearPowers"][1]["image"]["url"]))
        if len(player["headGear"]["additionalGearPowers"]) > 2:
            h_subs.append(utils.translate_gear_ability(player["headGear"]["additionalGearPowers"][2]["image"]["url"]))

        c_main = utils.translate_gear_ability(player["clothingGear"]["primaryGearPower"]["image"]["url"])
        c_subs = []
        if len(player["clothingGear"]["additionalGearPowers"]) > 0:
            c_subs.append(
                utils.translate_gear_ability(player["clothingGear"]["additionalGearPowers"][0]["image"]["url"]))
        if len(player["clothingGear"]["additionalGearPowers"]) > 1:
            c_subs.append(
                utils.translate_gear_ability(player["clothingGear"]["additionalGearPowers"][1]["image"]["url"]))
        if len(player["clothingGear"]["additionalGearPowers"]) > 2:
            c_subs.append(
                utils.translate_gear_ability(player["clothingGear"]["additionalGearPowers"][2]["image"]["url"]))

        s_main = utils.translate_gear_ability(player["shoesGear"]["primaryGearPower"]["image"]["url"])
        s_subs = []
        if len(player["shoesGear"]["additionalGearPowers"]) > 0:
            s_subs.append(utils.translate_gear_ability(player["shoesGear"]["additionalGearPowers"][0]["image"]["url"]))
        if len(player["shoesGear"]["additionalGearPowers"]) > 1:
            s_subs.append(utils.translate_gear_ability(player["shoesGear"]["additionalGearPowers"][1]["image"]["url"]))
        if len(player["shoesGear"]["additionalGearPowers"]) > 2:
            s_subs.append(utils.translate_gear_ability(player["shoesGear"]["additionalGearPowers"][2]["image"]["url"]))

        return h_main, h_subs, c_main, c_subs, s_main, s_subs

    @staticmethod
    def set_scoreboard(battle, tricolor=False):
        '''Returns lists of player dictionaries: our_team_players, their_team_players, and optionally third_team_players.'''

        # https://github.com/fetus-hina/stat.ink/wiki/Spl3-API:-Battle-%EF%BC%8D-Post#player-structure
        our_team_players, their_team_players, third_team_players = [], [], []

        for i, player in enumerate(battle["myTeam"]["players"]):
            p_dict = {}
            p_dict["me"] = "yes" if player["isMyself"] else "no"
            p_dict["name"] = player["name"]
            try:
                p_dict["number"] = str(player["nameId"])  # splashtag # - can contain alpha chars too... (why!!!)
            except KeyError:  # may not be present if first battle as "Player"
                pass
            p_dict["splashtag_title"] = player["byname"]  # splashtag title
            p_dict["weapon"] = utils.b64d(player["weapon"]["id"])
            p_dict["inked"] = player["paint"]
            p_dict["species"] = player["species"].lower()
            p_dict["rank_in_team"] = i + 1

            if player.get("crown"):
                p_dict["crown_type"] = "x"
            if "DRAGON" in player.get("festDragonCert", ""):
                if player["festDragonCert"] == "DRAGON":
                    p_dict["crown_type"] = "100x"
                elif player["festDragonCert"] == "DOUBLE_DRAGON":
                    p_dict["crown_type"] = "333x"

            if "result" in player and player["result"] is not None:
                p_dict["kill_or_assist"] = player["result"]["kill"]
                p_dict["assist"] = player["result"]["assist"]
                p_dict["kill"] = p_dict["kill_or_assist"] - p_dict["assist"]
                p_dict["death"] = player["result"]["death"]
                p_dict["special"] = player["result"]["special"]
                p_dict["signal"] = player["result"]["noroshiTry"]
                p_dict["disconnected"] = "no"
                p_dict["crown"] = "yes" if player.get("crown") == True else "no"

                # https://github.com/fetus-hina/stat.ink/wiki/Spl3-API:-Battle-%EF%BC%8D-Post#gears-structure
                gear_struct = {"headgear": {}, "clothing": {}, "shoes": {}}
                h_main, h_subs, c_main, c_subs, s_main, s_subs = STAT.populate_gear_abilities(player)
                gear_struct["headgear"] = {"primary_ability": h_main, "secondary_abilities": h_subs}
                gear_struct["clothing"] = {"primary_ability": c_main, "secondary_abilities": c_subs}
                gear_struct["shoes"] = {"primary_ability": s_main, "secondary_abilities": s_subs}
                p_dict["gears"] = gear_struct
            else:
                p_dict["disconnected"] = "yes"
            our_team_players.append(p_dict)

        team_nums = [0, 1] if tricolor else [0]
        for team_num in team_nums:
            for i, player in enumerate(battle["otherTeams"][team_num]["players"]):
                p_dict = {}
                p_dict["me"] = "no"
                p_dict["name"] = player["name"]
                try:
                    p_dict["number"] = str(player["nameId"])
                except:
                    pass
                p_dict["splashtag_title"] = player["byname"]
                p_dict["weapon"] = utils.b64d(player["weapon"]["id"])
                p_dict["inked"] = player["paint"]
                p_dict["species"] = player["species"].lower()
                p_dict["rank_in_team"] = i + 1

                if player.get("crown"):
                    p_dict["crown_type"] = "x"
                if "DRAGON" in player.get("festDragonCert", ""):
                    if player["festDragonCert"] == "DRAGON":
                        p_dict["crown_type"] = "100x"
                    elif player["festDragonCert"] == "DOUBLE_DRAGON":
                        p_dict["crown_type"] = "333x"

                if "result" in player and player["result"] is not None:
                    p_dict["kill_or_assist"] = player["result"]["kill"]
                    p_dict["assist"] = player["result"]["assist"]
                    p_dict["kill"] = p_dict["kill_or_assist"] - p_dict["assist"]
                    p_dict["death"] = player["result"]["death"]
                    p_dict["special"] = player["result"]["special"]
                    p_dict["signal"] = player["result"]["noroshiTry"]
                    p_dict["disconnected"] = "no"
                    p_dict["crown"] = "yes" if player.get("crown") == True else "no"

                    gear_struct = {"headgear": {}, "clothing": {}, "shoes": {}}
                    h_main, h_subs, c_main, c_subs, s_main, s_subs = STAT.populate_gear_abilities(player)
                    gear_struct["headgear"] = {"primary_ability": h_main, "secondary_abilities": h_subs}
                    gear_struct["clothing"] = {"primary_ability": c_main, "secondary_abilities": c_subs}
                    gear_struct["shoes"] = {"primary_ability": s_main, "secondary_abilities": s_subs}
                    p_dict["gears"] = gear_struct
                else:
                    p_dict["disconnected"] = "yes"
                if team_num == 0:
                    their_team_players.append(p_dict)
                elif team_num == 1:
                    third_team_players.append(p_dict)

        if tricolor:
            return our_team_players, their_team_players, third_team_players
        else:
            return our_team_players, their_team_players
