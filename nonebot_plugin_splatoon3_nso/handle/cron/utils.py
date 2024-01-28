from typing import Type

from nonebot import logger

from nonebot_plugin_splatoon3_nso.data.db_sqlite import UserTable

cron_logger = logger.bind(cron=True)


def user_remove_duplicates(lst: list[UserTable]):
    # 根据session_token值去重全部users
    result = []
    for u in lst:
        if u.session_token not in [r.session_token for r in result]:
            result.append(u)
    return result
