# (ↄ) 2017-2022 eli fessler (frozenpandaman), clovervidia
# https://github.com/frozenpandaman/s3s
# License: GPLv3
import httpx
from loguru import logger
import base64, hashlib, json, os, re, sys
import requests
from bs4 import BeautifulSoup
from ..utils import BOT_VERSION

S3S_VERSION = "unknown"
NSOAPP_VERSION = "unknown"
NSOAPP_VER_FALLBACK = "2.8.1"  # fallback
WEB_VIEW_VERSION = "unknown"
WEB_VIEW_VER_FALLBACK = "6.0.0-daea5c11"  # fallback

SPLATNET3_URL = "https://api.lp1.av5ja.srv.nintendo.net"
GRAPHQL_URL = SPLATNET3_URL + "/api/graphql"

F_USER_AGENT = f'splatoon3_bot/{BOT_VERSION}'
APP_USER_AGENT = 'Mozilla/5.0 (Linux; Android 11; Pixel 5) ' \
                 'AppleWebKit/537.36 (KHTML, like Gecko) ' \
                 'Chrome/94.0.4606.61 Mobile Safari/537.36'

global_client_dict: dict[httpx.Client] = {}


# 登录需要保持一段时间浏览器状态，在输入npf码完成登录后需要关闭session

def get_or_init_client(msg_id):
    """为每个登录会话创建唯一client，防止公共变量覆盖"""
    global global_client_dict
    client: httpx.Client = global_client_dict.get(msg_id)
    if client:
        return client
    else:
        client = httpx.Client()
        global_client_dict.update({msg_id: client})
        return client


def close_client(msg_id):
    """关闭client"""
    global global_client_dict
    client: httpx.Client = global_client_dict.get(msg_id)
    if client:
        client.close()
        global_client_dict.pop(msg_id)


def get_nsoapp_version(f_gen_url):
    '''Fetches the current Nintendo Switch Online app version from f API or the Apple App Store and sets it globally.'''

    global NSOAPP_VERSION
    if NSOAPP_VERSION != "unknown":  # already set
        return NSOAPP_VERSION
    else:
        try:  # try to get NSO version from f API
            f_conf_url = os.path.dirname(f_gen_url) + "/config"  # default endpoint for imink API
            f_conf_header = {'User-Agent': F_USER_AGENT}
            f_conf_rsp = httpx.get(f_conf_url, headers=f_conf_header)
            f_conf_json = json.loads(f_conf_rsp.text)
            ver = f_conf_json["nso_version"]

            NSOAPP_VERSION = ver

            return NSOAPP_VERSION
        except:  # fallback to apple app store
            try:
                page = httpx.get("https://apps.apple.com/us/app/nintendo-switch-online/id1234806557")
                soup = BeautifulSoup(page.text, 'html.parser')
                elt = soup.find("p", {"class": "whats-new__latest__version"})
                ver = elt.get_text().replace("Version ", "").strip()

                NSOAPP_VERSION = ver
                return NSOAPP_VERSION
            except:  # error with web request
                pass

            return NSOAPP_VER_FALLBACK


def get_web_view_ver(bhead=[], gtoken=""):
    """Finds & parses the SplatNet 3 main.js file to fetch the current site version and sets it globally."""

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
            home = httpx.get(SPLATNET3_URL, headers=app_head, cookies=app_cookies)
        except httpx.ConnectError:
            print("Could not connect to network. Please try again.")

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

        main_js_body = httpx.get(main_js_url, headers=app_head, cookies=app_cookies)
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


def log_in(ver, msg_id):
    """Logs in to a Nintendo Account and returns a session_token."""

    global S3S_VERSION
    S3S_VERSION = ver

    auth_state = base64.urlsafe_b64encode(os.urandom(36))

    auth_code_verifier = base64.urlsafe_b64encode(os.urandom(32))
    auth_cv_hash = hashlib.sha256()
    auth_cv_hash.update(auth_code_verifier.replace(b"=", b""))
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

    body = {
        'state': auth_state,
        'redirect_uri': 'npf71b963c1b7b6d119://auth',
        'client_id': '71b963c1b7b6d119',
        'scope': 'openid user user.birthday user.mii user.screenName',
        'response_type': 'session_token_code',
        'session_token_code_challenge': auth_code_challenge.replace(b"=", b""),
        'session_token_code_challenge_method': 'S256',
        'theme': 'login_form'
    }

    url = 'https://accounts.nintendo.com/connect/1.0.0/authorize'
    client = get_or_init_client(msg_id)
    r = client.get(url, headers=app_head, params=body)

    post_login = r.history[0].url

    print(
        "\nMake sure you have fully read the \"Token generation\" section of the readme before proceeding. To manually input a token instead, enter \"skip\" at the prompt below.")
    print("\nNavigate to this URL in your browser:")
    print(post_login)
    print("Log in, right click the \"Select this account\" button, copy the link address, and paste it below:")
    return post_login, auth_code_verifier


def login_2(use_account_url, auth_code_verifier):
    while True:
        try:
            if use_account_url == "skip":
                return "skip"
            session_token_code = re.search('de=(.*)&', use_account_url)
            return get_session_token(session_token_code.group(1), auth_code_verifier)
        except KeyboardInterrupt:
            print("\nBye!")
            return "skip"
        except AttributeError:
            print("Malformed URL. Please try again, or press Ctrl+C to exit.")
            print("URL:", end=' ')
            return "skip"
        except KeyError:  # session_token not found
            print("\nThe URL has expired. Please log out and back into your Nintendo Account and try again.")
            return "skip"
        except Exception as ex:
            print(f'ex: {ex}')
            return 'skip'


def get_session_token(session_token_code, auth_code_verifier, msg_id):
    """Helper function for log_in()."""

    nsoapp_version = get_nsoapp_version()

    app_head = {
        'User-Agent': f'OnlineLounge/{nsoapp_version} NASDKAPI Android',
        'Accept-Language': 'en-US',
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': '540',
        'Host': 'accounts.nintendo.com',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip'
    }

    body = {
        'client_id': '71b963c1b7b6d119',
        'session_token_code': session_token_code,
        'session_token_code_verifier': auth_code_verifier.replace(b"=", b"")
    }

    url = 'https://accounts.nintendo.com/connect/1.0.0/api/session_token'
    client = get_or_init_client(msg_id)
    r = client.post(url, headers=app_head, data=body)
    try:
        s_t = json.loads(r.text)["session_token"]
    except json.decoder.JSONDecodeError:
        print("Got non-JSON response from Nintendo (in api/session_token step). Please try again.")
        sys.exit(1)

    return s_t


async def get_gtoken(f_gen_url, session_token, ver):
    """Provided the session_token, returns a GameWebToken and account info."""

    if not session_token:
        raise ValueError('invalid_grant')

    nsoapp_version = get_nsoapp_version(f_gen_url)

    global S3S_VERSION
    S3S_VERSION = ver

    app_head = {
        'Host': 'accounts.nintendo.com',
        'Accept-Encoding': 'gzip',
        'Content-Type': 'application/json',
        'Content-Length': '436',
        'Accept': 'application/json',
        'Connection': 'Keep-Alive',
        'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 7.1.2)'
    }

    body = {
        'client_id': '71b963c1b7b6d119',
        'session_token': session_token,
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer-session-token'
    }

    url = "https://accounts.nintendo.com/connect/1.0.0/api/token"
    r = httpx.post(url, headers=app_head, json=body)
    id_response = json.loads(r.text)

    # get user info
    try:
        app_head = {
            'User-Agent': 'NASDKAPI; Android',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {id_response["access_token"]}',
            'Host': 'api.accounts.nintendo.com',
            'Connection': 'Keep-Alive',
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
    r = httpx.get(url, headers=app_head)
    user_info = json.loads(r.text)

    user_nickname = user_info["nickname"]
    user_lang = user_info["language"]
    user_country = user_info["country"]
    user_id = user_info["id"]

    # get access token
    body = {}
    try:
        access_token = id_response["id_token"]
        f, uuid, timestamp = call_f_api(access_token, 1, f_gen_url, user_id)

        parameter = {
            'f': f,
            'language': user_lang,
            'naBirthday': user_info["birthday"],
            'naCountry': user_country,
            'naIdToken': access_token,
            'requestId': uuid,
            'timestamp': timestamp
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
        'X-Platform': 'Android',
        'X-ProductVersion': nsoapp_version,
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': str(990 + len(f)),
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip',
        'User-Agent': f'com.nintendo.znca/{nsoapp_version}(Android/7.1.2)',
    }

    url = "https://api-lp1.znc.srv.nintendo.net/v3/Account/Login"
    r = httpx.post(url, headers=app_head, json=body)
    splatoon_token = json.loads(r.text)

    try:
        access_token = splatoon_token["result"]["webApiServerCredential"]["accessToken"]
        coral_user_id = splatoon_token["result"]["user"]["id"]
    except:
        # retry once if 9403/9599 error from nintendo
        try:
            f, uuid, timestamp = call_f_api(access_token, 1, f_gen_url, user_id)
            body["parameter"]["f"] = f
            body["parameter"]["requestId"] = uuid
            body["parameter"]["timestamp"] = timestamp
            app_head["Content-Length"] = str(990 + len(f))
            url = "https://api-lp1.znc.srv.nintendo.net/v3/Account/Login"
            r = httpx.post(url, headers=app_head, json=body)
            splatoon_token = json.loads(r.text)
            access_token = splatoon_token["result"]["webApiServerCredential"]["accessToken"]
            coral_user_id = splatoon_token["result"]["user"]["id"]
        except:
            logger.warning("Error from Nintendo (in Account/Login step):")
            logger.warning(json.dumps(splatoon_token, indent=2))
            logger.warning(
                "Try re-running the script. Or, if the NSO app has recently been updated, you may temporarily change `USE_OLD_NSOAPP_VER` to True at the top of iksm.py for a workaround.")
            return

        f, uuid, timestamp = call_f_api(access_token, 2, f_gen_url, user_id, coral_user_id=coral_user_id)

    # get web service token
    app_head = {
        'X-Platform': 'Android',
        'X-ProductVersion': nsoapp_version,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': '391',
        'Accept-Encoding': 'gzip',
        'User-Agent': f'com.nintendo.znca/{nsoapp_version}(Android/7.1.2)'
    }

    body = {}
    parameter = {
        'f': f,
        'id': 4834290508791808,
        'registrationToken': access_token,
        'requestId': uuid,
        'timestamp': timestamp
    }
    body["parameter"] = parameter

    url = "https://api-lp1.znc.srv.nintendo.net/v2/Game/GetWebServiceToken"
    r = httpx.post(url, headers=app_head, json=body)
    web_service_resp = json.loads(r.text)

    try:
        web_service_token = web_service_resp["result"]["accessToken"]
    except:
        # retry once if 9403/9599 error from nintendo
        try:
            f, uuid, timestamp = call_f_api(access_token, 2, f_gen_url, user_id, coral_user_id=coral_user_id)
            body["parameter"]["f"] = f
            body["parameter"]["requestId"] = uuid
            body["parameter"]["timestamp"] = timestamp
            url = "https://api-lp1.znc.srv.nintendo.net/v2/Game/GetWebServiceToken"
            r = httpx.post(url, headers=app_head, json=body)
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


def get_bullet(web_service_token, app_user_agent, user_lang, user_country):
    """Given a gtoken, returns a bulletToken."""

    app_head = {
        'Content-Length': '0',
        'Content-Type': 'application/json',
        'Accept-Language': user_lang,
        'User-Agent': app_user_agent,
        'X-Web-View-Ver': get_web_view_ver(),
        'X-NACOUNTRY': user_country,
        'Accept': '*/*',
        'Origin': SPLATNET3_URL,
        'X-Requested-With': 'com.nintendo.znca'
    }
    app_cookies = {
        '_gtoken': web_service_token,  # X-GameWebToken
        '_dnt': '1'  # Do Not Track
    }
    url = f'{SPLATNET3_URL}/api/bullet_tokens'
    r = httpx.post(url, headers=app_head, cookies=app_cookies)

    if r.status_code == 401:
        print("Unauthorized error (ERROR_INVALID_GAME_WEB_TOKEN). Cannot fetch tokens at this time.")
        sys.exit(1)
    elif r.status_code == 403:
        print("Forbidden error (ERROR_OBSOLETE_VERSION). Cannot fetch tokens at this time.")
        sys.exit(1)
    elif r.status_code == 204:  # No Content, USER_NOT_REGISTERED
        print("Cannot access SplatNet 3 without having played online.")
        sys.exit(1)

    try:
        bullet_resp = json.loads(r.text)
        bullet_token = bullet_resp["bulletToken"]
    except (json.decoder.JSONDecodeError, TypeError):
        print("Got non-JSON response from Nintendo (in api/bullet_tokens step):")
        print(r.text)
        bullet_token = ""
    except:
        print("Error from Nintendo (in api/bullet_tokens step):")
        print(json.dumps(bullet_resp, indent=2))
        sys.exit(1)

    return bullet_token


def call_f_api(access_token, step, f_gen_url, user_id, coral_user_id=None):
    '''Passes naIdToken & user ID to f generation API (default: imink) & fetches response (f token, UUID, timestamp).'''

    api_head = {}
    api_body = {}
    api_response = None
    try:
        api_head = {
            'User-Agent': F_USER_AGENT,
            'Content-Type': 'application/json; charset=utf-8',
            'X-znca-Platform': 'Android',
            'X-znca-Version': NSOAPP_VERSION
        }
        api_body = {  # 'timestamp' & 'request_id' (uuid v4) set automatically
            'token': access_token,
            'hash_method': step,  # 1 = coral (NSO) token, 2 = webservicetoken
            'na_id': user_id
        }
        if step == 2 and coral_user_id is not None:
            api_body["coral_user_id"] = coral_user_id

        api_response = httpx.post(f_gen_url, data=api_body, headers=api_head)
        resp = json.loads(api_response.text)

        logger.debug(f"get f generation: \n{f_gen_url}\n{json.dumps(api_head)}\n{json.dumps(api_body)}")
        f = resp["f"]
        uuid = resp["request_id"]
        timestamp = resp["timestamp"]
        return f, uuid, timestamp
    except:
        try:  # if api_response never gets set
            logger.warning(f"Error during f generation: \n{f_gen_url}\n{json.dumps(api_head)}\n{json.dumps(api_body)}")
            if api_response and api_response.text:
                logger.error(
                    f"Error during f generation:\n{json.dumps(json.loads(api_response.text), indent=2, ensure_ascii=False)}")
            else:
                logger.error(f"Error during f generation: Error {api_response.status_code}.")
        except:
            logger.error(f"Couldn't connect to f generation API ({f_gen_url}). Please try again later.")

        return


if __name__ == "__main__":
    print("This program cannot be run alone. See https://github.com/frozenpandaman/s3s")
    sys.exit(0)
