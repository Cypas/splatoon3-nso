from nonebot import logger

from ...data.db_sqlite import UserTable

cron_logger = logger.bind(cron=True)


def user_remove_duplicates(lst: list[UserTable]):
    # 根据game_sp_id值去重全部users
    result = []
    for u in lst:
        if u.game_sp_id:
            if u.game_sp_id not in [r.game_sp_id for r in result]:
                result.append(u)
        else:
            # 没有sp_id的用户，可能是登录时网络错误导致没有token更新成功，在写日报时进行更新
            # 根据session_token进行去重
            if u.session_token not in [r.session_token for r in result]:
                result.append(u)
    return result
