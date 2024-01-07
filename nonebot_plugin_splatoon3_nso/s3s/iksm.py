# (ↄ) 2017-2022 eli fessler (frozenpandaman), clovervidia
# https://github.com/frozenpandaman/s3s
# License: GPLv3

from loguru import logger
import base64, hashlib, json, os, re, sys
import requests
from bs4 import BeautifulSoup
from ..utils import BOT_VERSION

S3S_VERSION = "unknown"
NSOAPP_VERSION = "2.8.1"


def get_nsoapp_version():
	'''Fetches the current Nintendo Switch Online app version from the Apple App Store.'''

	return NSOAPP_VERSION
	try:
		page = requests.get("https://apps.apple.com/us/app/nintendo-switch-online/id1234806557")
		soup = BeautifulSoup(page.text, 'html.parser')
		elt = soup.find("p", {"class": "whats-new__latest__version"})
		ver = elt.get_text().replace("Version ", "").strip()
		return ver
	except:
		return NSOAPP_VERSION


async def get_gtoken(f_gen_url, session_token, ver):
	"""Provided the session_token, returns a GameWebToken and account info."""

	if not session_token:
		raise ValueError('invalid_grant')

	nsoapp_version = get_nsoapp_version()

	global S3S_VERSION
	S3S_VERSION = ver

	app_head = {
		'Host':            'accounts.nintendo.com',
		'Accept-Encoding': 'gzip',
		'Content-Type':    'application/json',
		'Content-Length':  '436',
		'Accept':          'application/json',
		'Connection':      'Keep-Alive',
		'User-Agent':      'Dalvik/2.1.0 (Linux; U; Android 7.1.2)'
	}

	body = {
		'client_id':     '71b963c1b7b6d119',
		'session_token': session_token,
		'grant_type':    'urn:ietf:params:oauth:grant-type:jwt-bearer-session-token'
	}

	url = "https://accounts.nintendo.com/connect/1.0.0/api/token"
	r = requests.post(url, headers=app_head, json=body)
	id_response = json.loads(r.text)

	# get user info
	try:
		app_head = {
			'User-Agent':      'NASDKAPI; Android',
			'Content-Type':    'application/json',
			'Accept':          'application/json',
			'Authorization':   f'Bearer {id_response["access_token"]}',
			'Host':            'api.accounts.nintendo.com',
			'Connection':      'Keep-Alive',
			'Accept-Encoding': 'gzip'
		}
	except:
		logger.warning("Not a valid authorization request. Please delete config.txt and try again.")
		logger.warning("Error from Nintendo (in api/token step):")
		logger.warning(json.dumps(id_response, indent=2))
		if id_response.get('error') == 'invalid_grant':
			raise ValueError('invalid_grant')
		return

	url = "https://api.accounts.nintendo.com/2.0.0/users/me"
	r = requests.get(url, headers=app_head)
	user_info = json.loads(r.text)

	user_nickname = user_info["nickname"]
	user_lang     = user_info["language"]
	user_country  = user_info["country"]
	user_id       = user_info["id"]

	# get access token
	body = {}
	try:
		id_token = id_response["id_token"]
		f, uuid, timestamp = call_imink_api(id_token, 1, f_gen_url, user_id)

		parameter = {
			'f':          f,
			'language':   user_lang,
			'naBirthday': user_info["birthday"],
			'naCountry':  user_country,
			'naIdToken':  id_token,
			'requestId':  uuid,
			'timestamp':  timestamp
		}
	except SystemExit:
		return
	except:
		logger.warning("Error(s) from Nintendo:")
		logger.warning(json.dumps(id_response, indent=2))
		logger.warning(json.dumps(user_info, indent=2))
		return
	body["parameter"] = parameter

	app_head = {
		'X-Platform':       'Android',
		'X-ProductVersion': nsoapp_version,
		'Content-Type':     'application/json; charset=utf-8',
		'Content-Length':   str(990 + len(f)),
		'Connection':       'Keep-Alive',
		'Accept-Encoding':  'gzip',
		'User-Agent':       f'com.nintendo.znca/{nsoapp_version}(Android/7.1.2)',
	}

	url = "https://api-lp1.znc.srv.nintendo.net/v3/Account/Login"
	r = requests.post(url, headers=app_head, json=body)
	splatoon_token = json.loads(r.text)

	try:
		id_token = splatoon_token["result"]["webApiServerCredential"]["accessToken"]
		coral_user_id = splatoon_token["result"]["user"]["id"]
	except:
		# retry once if 9403/9599 error from nintendo
		try:
			f, uuid, timestamp = call_imink_api(id_token, 1, f_gen_url, user_id)
			body["parameter"]["f"]         = f
			body["parameter"]["requestId"] = uuid
			body["parameter"]["timestamp"] = timestamp
			app_head["Content-Length"]     = str(990 + len(f))
			url = "https://api-lp1.znc.srv.nintendo.net/v3/Account/Login"
			r = requests.post(url, headers=app_head, json=body)
			splatoon_token = json.loads(r.text)
			id_token = splatoon_token["result"]["webApiServerCredential"]["accessToken"]
			coral_user_id = splatoon_token["result"]["user"]["id"]
		except:
			logger.warning("Error from Nintendo (in Account/Login step):")
			logger.warning(json.dumps(splatoon_token, indent=2))
			logger.warning("Re-running the script usually fixes this.")
			return

		f, uuid, timestamp = call_imink_api(id_token, 2, f_gen_url, user_id, coral_user_id=coral_user_id)

	# get web service token
	app_head = {
		'X-Platform':       'Android',
		'X-ProductVersion': nsoapp_version,
		'Authorization':    f'Bearer {id_token}',
		'Content-Type':     'application/json; charset=utf-8',
		'Content-Length':   '391',
		'Accept-Encoding':  'gzip',
		'User-Agent':       f'com.nintendo.znca/{nsoapp_version}(Android/7.1.2)'
	}

	body = {}
	parameter = {
		'f':                 f,
		'id':                4834290508791808,
		'registrationToken': id_token,
		'requestId':         uuid,
		'timestamp':         timestamp
	}
	body["parameter"] = parameter

	url = "https://api-lp1.znc.srv.nintendo.net/v2/Game/GetWebServiceToken"
	r = requests.post(url, headers=app_head, json=body)
	web_service_resp = json.loads(r.text)

	try:
		web_service_token = web_service_resp["result"]["accessToken"]
	except:
		# retry once if 9403/9599 error from nintendo
		try:
			f, uuid, timestamp = call_imink_api(id_token, 2, f_gen_url, user_id, coral_user_id=coral_user_id)
			body["parameter"]["f"]         = f
			body["parameter"]["requestId"] = uuid
			body["parameter"]["timestamp"] = timestamp
			url = "https://api-lp1.znc.srv.nintendo.net/v2/Game/GetWebServiceToken"
			r = requests.post(url, headers=app_head, json=body)
			web_service_resp = json.loads(r.text)
			web_service_token = web_service_resp["result"]["accessToken"]
		except:
			logger.warning("Error from Nintendo (in Game/GetWebServiceToken step):")
			logger.warning(json.dumps(web_service_resp, indent=2))
			if web_service_resp.get('errorMessage') == 'Membership required error.':
				logger.warning(user_info)
				nickname = user_info.get('nickname')
				raise ValueError(f'Membership required error.|{nickname}')
			return

	return web_service_token, user_nickname, user_lang, user_country, user_info


def call_imink_api(id_token, step, f_gen_url, user_id, coral_user_id=None):
	"""Passes in an naIdToken to the f API and fetches the response (comprised of an f token, UUID, and timestamp)."""

	api_head = {}
	api_body = {}
	api_response = None
	try:
		api_head = {
			'User-Agent':   f'splatoon3_bot/{BOT_VERSION}',
			'Content-Type': 'application/json; charset=utf-8',
			'X-znca-Platform': 'Android',
			'X-znca-Version': NSOAPP_VERSION
		}
		api_body = {
			'token':       id_token,
			'hash_method':  step,
			'na_id':       user_id
		}
		if step == 2 and coral_user_id is not None:
			api_body["coral_user_id"] = str(coral_user_id)

		api_response = requests.post(f_gen_url, data=json.dumps(api_body), headers=api_head)
		resp = json.loads(api_response.text)

		logger.debug(f"get f generation: \n{f_gen_url}\n{json.dumps(api_head)}\n{json.dumps(api_body)}")
		f = resp["f"]
		uuid = resp["request_id"]
		timestamp = resp["timestamp"]
		return f, uuid, timestamp
	except:
		try: # if api_response never gets set
			logger.warning(f"Error during f generation: \n{f_gen_url}\n{json.dumps(api_head)}\n{json.dumps(api_body)}")
			if api_response and api_response.text:
				logger.error(f"Error during f generation:\n{json.dumps(json.loads(api_response.text), indent=2, ensure_ascii=False)}")
			else:
				logger.error(f"Error during f generation: Error {api_response.status_code}.")
		except:
			logger.error(f"Couldn't connect to f generation API ({f_gen_url}). Please try again.")

		return


if __name__ == "__main__":
	print("This program cannot be run alone. See https://github.com/frozenpandaman/s3s")
	sys.exit(0)
