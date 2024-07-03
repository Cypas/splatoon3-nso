import os

BOT_VERSION = "2.7.6"
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
