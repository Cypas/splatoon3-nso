# (ↄ) 2017-2022 eli fessler (frozenpandaman), clovervidia
# https://github.com/frozenpandaman/s3s
# License: GPLv3

import base64
import datetime
import json
import sys
import uuid

SPLATNET3_URL = "https://api.lp1.av5ja.srv.nintendo.net"
GRAPHQL_URL = SPLATNET3_URL + "/api/graphql"
S3S_NAMESPACE = uuid.UUID('b3a2dbf5-2c09-4792-b78c-00b548b70aeb')

SUPPORTED_KEYS = [
    "ignore_private",
    "ignore_private_jobs",
    "app_user_agent",
    "force_uploads",
    "errors_pass_silently",
    "old_export_format"
]

# SHA256 hash database for SplatNet 3 GraphQL queries
# full list: https://github.com/samuelthomas2774/nxapi/discussions/11#discussioncomment-3614603
translate_rid = {
    'HomeQuery': '51fc56bbf006caf37728914aa8bc0e2c86a80cf195b4d4027d6822a3623098a8',  # 主页
    'LatestBattleHistoriesQuery': 'b24d22fd6cb251c515c2b90044039698aa27bc1fab15801d83014d919cd45780',  # 对战 - 最近
    'RegularBattleHistoriesQuery': '2fe6ea7a2de1d6a888b7bd3dbeb6acc8e3246f055ca39b80c4531bbcd0727bba',  # 对战 - 一般(涂地)
    'BankaraBattleHistoriesQuery': '9863ea4744730743268e2940396e21b891104ed40e2286789f05100b45a0b0fd',  # 对战 - 蛮颓
    'PrivateBattleHistoriesQuery': 'fef94f39b9eeac6b2fac4de43bc0442c16a9f2df95f4d367dd8a79d7c5ed5ce7',  # 对战 - 私房
    'XBattleHistoriesQuery': 'eb5996a12705c2e94813a62e05c0dc419aad2811b8d49d53e5732290105559cb',  # 对战 - X比赛
    'VsHistoryDetailQuery': '20f88b10d0b1d264fcb2163b0866de26bbf6f2b362f397a0258a75b7fa900943',
    # 通过比赛id详查  参数2:"vsResultId" 参数3:比赛id
    'CoopHistoryQuery': '0f8c33970a425683bb1bdecca50a0ca4fb3c3641c0b2a1237aedfde9c0cb2b8f',  # 鲑鱼跑
    'CoopHistoryDetailQuery': 'f2d55873a9281213ae27edc171e2b19131b3021a2ae263757543cdd3bf015cc8',
    # 通过打工id详查 参数2:"coopHistoryDetailId" 参数3:打工id
    'MyOutfitCommonDataEquipmentsQuery': '45a4c343d973864f7bb9e9efac404182be1d48cf2181619505e9b7cd3b56a6e8',
    # 主页 - 武器  获取全部武器数据
    'FriendsList': 'ea1297e9bb8e52404f52d89ac821e1d73b726ceef2fd9cc8d6b38ab253428fb3',  # 好友列表
    'HistorySummary': '0a62c0152f27c4218cf6c87523377521c2cff76a4ef0373f2da3300079bf0388',  # 主页 - 历史 -总览
    'TotalQuery': '2a9302bdd09a13f8b344642d4ed483b9464f20889ac17401e993dfa5c2bb3607',  # 统计查询  nso没有这个页面
    'XRankingQuery': 'a5331ed228dbf2e904168efe166964e2be2b00460c578eee49fc0bc58b4b899c',  # 主页 - x排名
    'ScheduleQuery': '9b6b90568f990b2a14f04c25dd6eb53b35cc12ac815db85ececfccee64215edd',  # 日程
    'StageRecordsQuery': 'c8b31c491355b4d889306a22bd9003ac68f8ce31b2d5345017cdd30a2c8056f3',  # 主页 - 场地 (查各地图胜率)
    'EventBattleHistoriesQuery': 'e47f9aac5599f75c842335ef0ab8f4c640e8bf2afe588a3b1d4b480ee79198ac',  # 对战 - 活动
    'EventListQuery': '875a827a6e460c3cd6b1921e6a0872d8b95a1fce6d52af79df67734c5cc8b527',  # 主页 - 活动比赛
    'EventBoardQuery': 'ad4097d5fb900b01f12dffcb02228ef6c20ddbfba41f0158bb91e845335c708e',
    # 日程 - 活动比赛 - 详细排行榜   参数2:"eventMatchRankingPeriodId" 参数3:top_id
    'CoopPagerLatestCoopQuery': 'bc8a3d48e91d5d695ef52d52ae466920670d4f4381cb288cd570dc8160250457',
    # 打工页面获取最新打工数据，但数据其实还是输出的全部打工列表
    'PagerLatestVsDetailQuery': '73462e18d464acfdf7ac36bde08a1859aa2872a90ed0baed69c94864c20de046',  # 查询最新一局的对战id
    'CoopStatistics': '56f989a59643642e0799c90d3f6d0457f5f5f72d4444dfae87043c4a23d13043',  # 主页 - 打工  打工统计数据
    'XRanking500Query': '90932ee3357eadab30eb11e9d6b4fe52d6b35fde91b5c6fd92ba4d6159ea1cb7'  # 主页-x排名 - 顶级500强玩家
}


def set_noun(which):
    """Returns the term to be used when referring to the type of results in question."""

    if which == "both":
        return "battles/jobs"
    elif which == "salmon":
        return "jobs"
    else:  # "ink"
        return "battles"


def b64d(string):
    """Base64 decode a string and cut off the SplatNet prefix."""

    thing_id = base64.b64decode(string).decode('utf-8')
    thing_id = thing_id.replace("VsStage-", "")
    thing_id = thing_id.replace("VsMode-", "")
    thing_id = thing_id.replace("CoopStage-", "")
    thing_id = thing_id.replace("CoopGrade-", "")
    thing_id = thing_id.replace("CoopEnemy-", "")
    thing_id = thing_id.replace("CoopEventWave-", "")
    thing_id = thing_id.replace("CoopUniform-", "")
    thing_id = thing_id.replace("SpecialWeapon-", "")
    if "Weapon-" in thing_id:
        thing_id = thing_id.replace("Weapon-", "")
        if len(thing_id) == 5 and thing_id[:1] == "2" and thing_id[-3:] == "900":  # grizzco weapon ID from a hacker
            return ""

    if thing_id[:15] == "VsHistoryDetail" or thing_id[:17] == "CoopHistoryDetail" or thing_id[:8] == "VsPlayer":
        return thing_id  # string
    else:
        return int(thing_id)  # integer


def epoch_time(time_string):
    """Converts a playedTime string into an integer representing the epoch time."""

    utc_time = datetime.datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%SZ")
    _epoch_time = int((utc_time - datetime.datetime(1970, 1, 1)).total_seconds())
    return _epoch_time


def gen_graphql_body(sha256hash, varname=None, varvalue=None):
    """Generates a JSON dictionary, specifying information to retrieve, to send with GraphQL requests."""
    great_passage = {
        "extensions": {
            "persistedQuery": {
                "sha256Hash": sha256hash,
                "version": 1
            }
        },
        "variables": {}
    }

    if varname is not None and varvalue is not None:
        great_passage["variables"][varname] = varvalue

    return json.dumps(great_passage)


def custom_key_exists(key, config_data, value=True):
    """Checks if a given custom key exists in config.txt and is set to the specified value (true by default)."""

    # https://github.com/frozenpandaman/s3s/wiki/config-keys
    if key not in ["ignore_private", "app_user_agent", "force_uploads"]:
        print("(!) Checking unexpected custom key")
    return str(config_data.get(key, None)).lower() == str(value).lower()


if __name__ == "__main__":
    print("This program cannot be run alone. See https://github.com/frozenpandaman/s3s")
    sys.exit(0)
