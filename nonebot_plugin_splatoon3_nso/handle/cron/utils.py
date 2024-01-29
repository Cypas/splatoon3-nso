from typing import Type

from nonebot import logger

from ...data.db_sqlite import UserTable

cron_logger = logger.bind(cron=True)


def user_remove_duplicates(lst: list[UserTable]):
    # 根据game_sp_id值去重全部users
    result = []
    for u in lst:
        if u.game_sp_id and u.game_sp_id not in [r.game_sp_id for r in result]:
            result.append(u)
    return result
