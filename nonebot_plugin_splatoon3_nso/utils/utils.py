import base64
import io
import json
import os
import random
import time
from datetime import timedelta, datetime, timezone

from PIL import Image

BOT_VERSION = "3.1.1"
DIR_RESOURCE = f"{os.path.abspath(os.path.join(__file__, os.pardir, os.pardir))}/resource"
plugin_release_time = "2024-06-24 04:35:58"  # 预留  2.0.0重构版nso插件发布时间，预计发布时对全部用户先显示一周，之后再判断用户创建时间


def multiple_replace(text, _dict):
    """批量替换文本"""
    for key in _dict:
        text = text.replace(key, _dict[key])
    return text


def init_path(path_folder):
    """初始化文件夹路径"""
    if not os.path.exists(path_folder):
        os.mkdir(path_folder)


def get_msg_id(platform, user_id):
    """获取 msg_id 字符串，提供统一格式"""
    msg_id = f"{platform}-{user_id}"
    return msg_id


def trigger_with_probability():
    """
    该函数有1/100的概率返回True（触发）
    """
    return random.random() < 0.01


def get_image_size(img_data):
    """
    通过pillow库获取图片宽高数据
    """
    image = Image.open(io.BytesIO(img_data))
    width, height = image.size
    image.close()
    return width, height


def get_jwt_exp_info(jwt_token: str) -> dict:
    """
    解析JWT过期信息，返回包含剩余秒数、时间戳、到期日期的字典
    :param jwt_token: JWT令牌
    :return: 字典，示例：
        {"remaining_seconds": 3600, "exp_ts": 1735683600, "exp_date": "2026-02-04 15:30:00"}
        已过期/无效：{"remaining_seconds": 0, "exp_ts": 0, "exp_date": "已过期"}
    """
    try:
        jwt_parts = jwt_token.split('.')
        if len(jwt_parts) != 3:
            raise ValueError("JWT格式错误")
        payload_b64 = jwt_parts[1]
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
        exp = payload.get('exp')
        if not isinstance(exp, (int, float)):
            raise ValueError("无有效exp")

        current_ts = int(time.time())
        exp_ts = int(exp)
        remaining_seconds = exp_ts - current_ts if exp_ts > current_ts else 0
        # 时间戳转东八区日期
        tz_utc8 = timezone(timedelta(hours=8))
        exp_date = datetime.fromtimestamp(exp_ts, tz_utc8).strftime(
            "%Y-%m-%d %H:%M:%S") if remaining_seconds > 0 else "已过期"

        return {
            "remaining_seconds": remaining_seconds,
            "exp_ts": exp_ts if remaining_seconds > 0 else 0,
            "exp_date": exp_date
        }
    except Exception as e:
        print(f"解析JWT失败：{e}")
        return {"remaining_seconds": 0, "exp_ts": 0, "exp_date": "已过期"}


def get_file_bytes(file_name: str) -> bytes:
    """
    取静态资源目录下的指定文件bytes
    """
    with open(f"{DIR_RESOURCE}/{file_name}", "rb") as f:
        return f.read()


def game_name_replace(game_name: str) -> str:
    """
    玩家游戏名称替换 防止干扰markdown表格渲染
    """
    d = {
        "`": "&#96;",
        "|": "&#124;"
    }
    new_game_name = multiple_replace(game_name, d)
    return new_game_name


MSG_HELP = f"""
/me - show your info
/friends - show splatoon3 online friends
/ns_friends - show online friends
/last - show the last battle or coop
/start_push - start push mode
/x_top - show X Top Players
/screen_shot - ss, get screen shot of SplatNet

settings:
/set_stat_key - set stat.ink api_key for post data
/sync_now - sync data to stat.ink now
/show_db_info - show db info

/help - show this help message {BOT_VERSION}
https://docs.qq.com/sheet/DUkZHRWtCUkR0d2Nr?tab=BB08J2
"""

MSG_HELP_CN = f'''机器人使用说明
命令起始字符 / 或 、

常用指令:
/help - 显示此帮助信息 {BOT_VERSION}
/login - 登录喷喷账号
/report - 获取昨天或指定日期的日报数据
/last - 显示最近一场对战或打工
/friends - 显示在线的喷喷好友
/me - 显示你的喷喷信息


更多指令:
https://docs.qq.com/sheet/DUkZHRWtCUkR0d2Nr?tab=BB08J2
'''

MSG_HELP_QQ = f'''机器人使用说明
命令起始字符 / 或 、

/help - 显示此帮助信息 {BOT_VERSION}
/login - 登录喷喷账号
/last - 显示最近一场对战或打工
/me - 显示你的喷喷信息

'''
