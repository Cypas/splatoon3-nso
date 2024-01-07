# (ↄ) 2017-2022 eli fessler (frozenpandaman), clovervidia
# https://github.com/frozenpandaman/s3s
# License: GPLv3

import base64, datetime, json, re, sys, uuid
import requests
from bs4 import BeautifulSoup

SPLATNET3_URL = "https://api.lp1.av5ja.srv.nintendo.net"
GRAPHQL_URL = "https://api.lp1.av5ja.srv.nintendo.net/api/graphql"
WEB_VIEW_VERSION = "6.0.0-daea5c11"  # fallback
S3S_NAMESPACE = uuid.UUID('b3a2dbf5-2c09-4792-b78c-00b548b70aeb')

# SHA256 hash database for SplatNet 3 GraphQL queries
# full list: https://github.com/samuelthomas2774/nxapi/discussions/11#discussioncomment-3614603
translate_rid = {
	'HomeQuery':                         '51fc56bbf006caf37728914aa8bc0e2c86a80cf195b4d4027d6822a3623098a8', # blank vars
	'LatestBattleHistoriesQuery':        'b24d22fd6cb251c515c2b90044039698aa27bc1fab15801d83014d919cd45780', # INK / blank vars - query1
	'RegularBattleHistoriesQuery':       '2fe6ea7a2de1d6a888b7bd3dbeb6acc8e3246f055ca39b80c4531bbcd0727bba', # INK / blank vars - query1
	'BankaraBattleHistoriesQuery':       '9863ea4744730743268e2940396e21b891104ed40e2286789f05100b45a0b0fd', # INK / blank vars - query1
	'PrivateBattleHistoriesQuery':       'fef94f39b9eeac6b2fac4de43bc0442c16a9f2df95f4d367dd8a79d7c5ed5ce7', # INK / blank vars - query1
	'XBattleHistoriesQuery':             'eb5996a12705c2e94813a62e05c0dc419aad2811b8d49d53e5732290105559cb', # INK / blank vars - query1
	'VsHistoryDetailQuery':              'f893e1ddcfb8a4fd645fd75ced173f18b2750e5cfba41d2669b9814f6ceaec46', # INK / req "vsResultId" - query2
	'CoopHistoryQuery':                  '0f8c33970a425683bb1bdecca50a0ca4fb3c3641c0b2a1237aedfde9c0cb2b8f', # SR  / blank vars - query1
	'CoopHistoryDetailQuery':            '42262d241291d7324649e21413b29da88c0314387d8fdf5f6637a2d9d29954ae', # SR  / req "coopHistoryDetailId" - query2
	'MyOutfitCommonDataEquipmentsQuery': '45a4c343d973864f7bb9e9efac404182be1d48cf2181619505e9b7cd3b56a6e8', # for Lean's seed checker
	'FriendsList':                       'ea1297e9bb8e52404f52d89ac821e1d73b726ceef2fd9cc8d6b38ab253428fb3',
	'HistorySummary':                    '0a62c0152f27c4218cf6c87523377521c2cff76a4ef0373f2da3300079bf0388',
	'TotalQuery':                        '2a9302bdd09a13f8b344642d4ed483b9464f20889ac17401e993dfa5c2bb3607',
	'XRankingQuery':                     'a5331ed228dbf2e904168efe166964e2be2b00460c578eee49fc0bc58b4b899c',
	'ScheduleQuery':                     '9b6b90568f990b2a14f04c25dd6eb53b35cc12ac815db85ececfccee64215edd',
	'StageRecordsQuery':                 'c8b31c491355b4d889306a22bd9003ac68f8ce31b2d5345017cdd30a2c8056f3',
	'EventBattleHistoriesQuery':         'e47f9aac5599f75c842335ef0ab8f4c640e8bf2afe588a3b1d4b480ee79198ac',
	'EventListQuery':                    '875a827a6e460c3cd6b1921e6a0872d8b95a1fce6d52af79df67734c5cc8b527',
	'EventBoardQuery':                   'ad4097d5fb900b01f12dffcb02228ef6c20ddbfba41f0158bb91e845335c708e',
}

def get_web_view_ver():
	'''Find & parse the SplatNet 3 main.js file for the current site version.'''

	splatnet3_home = requests.get(SPLATNET3_URL)
	soup = BeautifulSoup(splatnet3_home.text, "html.parser")

	main_js = soup.select_one("script[src*='static']")
	if not main_js:
		return WEB_VIEW_VERSION

	main_js_url = SPLATNET3_URL + main_js.attrs["src"]
	main_js_body = requests.get(main_js_url)

	match = re.search(r"\b(?P<revision>[0-9a-f]{40})\b.*revision_info_not_set\"\),.*?=\"(?P<version>\d+\.\d+\.\d+)", main_js_body.text)
	if not match:
		return WEB_VIEW_VERSION

	version, revision = match.group("version"), match.group("revision")
	return f"{version}-{revision[:8]}"


def set_noun(which):
	'''Returns the term to be used when referring to the type of results in question.'''

	if which == "both":
		return "battles/jobs"
	elif which == "salmon":
		return "jobs"
	else: # "ink"
		return "battles"


def b64d(string):
	'''Base64 decode a string and cut off the SplatNet prefix.'''

	thing_id = base64.b64decode(string).decode('utf-8')
	thing_id = thing_id.replace("VsStage-", "")
	thing_id = thing_id.replace("VsMode-", "")
	thing_id = thing_id.replace("Weapon-", "")
	thing_id = thing_id.replace("CoopStage-", "")
	thing_id = thing_id.replace("CoopGrade-", "")
	if thing_id[:15] == "VsHistoryDetail" or thing_id[:17] == "CoopHistoryDetail":
		return thing_id # string
	else:
		return int(thing_id) # integer


def epoch_time(time_string):
	'''Converts a playedTime string into an int representing the epoch time.'''

	utc_time = datetime.datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%SZ")
	epoch_time = int((utc_time - datetime.datetime(1970, 1, 1)).total_seconds())
	return epoch_time


def gen_graphql_body(sha256hash, varname=None, varvalue=None):
	'''Generates a JSON dictionary, specifying information to retrieve, to send with GraphQL requests.'''
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
	'''Checks if a given custom key exists in config.txt and is set to the specified value (true by default).'''

	# https://github.com/frozenpandaman/s3s/wiki/config-keys
	if key not in ["ignore_private", "app_user_agent", "force_uploads"]:
		print("(!) Checking unexpected custom key")
	return True if key in config_data and config_data[key].lower() == str(value).lower() else False


if __name__ == "__main__":
	print("This program cannot be run alone. See https://github.com/frozenpandaman/s3s")
	sys.exit(0)
