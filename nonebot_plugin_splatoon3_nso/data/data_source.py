import copy

from loguru import logger
from sqlalchemy import text

from .db_sqlite import DBSession, DIR_TEMP_IMAGE, DBSession_Friends, UserTable
from .utils import model_get_or_set_temp_image, get_insert_or_update_obj, GlobalUserInfo

global_user_info_dict: dict[str:GlobalUserInfo] = {}  # 用于缓存今日已使用过指令的用户，并为这些活跃用户定期更新token


async def model_get_temp_image_path(_type, name, link) -> str:
    """获取缓存文件路径"""
    row = await model_get_or_set_temp_image(_type, name, link)
    # logger.info(f"row为{row.__dict__}")
    file_name = row.file_name
    return f"{DIR_TEMP_IMAGE}/{_type}/{file_name}"


def model_clean_db_cache():
    """整理数据库内存碎片"""
    session = DBSession()
    session.execute(text("VACUUM"))
    session.commit()
    session.close()

    session2 = DBSession_Friends()
    session2.execute(text("VACUUM"))
    session2.commit()
    session2.close()


def model_get_or_set_user(platform, user_id, **kwargs) -> UserTable:
    """获取或插入或更新user信息"""
    logger.debug(f'get_or_set_user: {kwargs}')
    try:
        session = DBSession()
        filter_dict = {"platform": platform, "user_id": user_id}
        user = get_insert_or_update_obj(UserTable, filter_dict, platform=platform, user_id=user_id, **kwargs)
        session.add(copy.deepcopy(user))
        session.commit()
        session.close()
        return user

    except Exception as e:
        logger.error(f'get_or_set_user error: {e}')
        return None


def model_get_all_user():
    """获取全部用户"""
    session = DBSession()
    users = session.query(UserTable).all()
    new_users = copy.deepcopy(users)
    session.commit()
    session.close()
    return new_users


def dict_get_or_set_user_info(platform, user_id, **kwargs):
    """获取 或 更新 用户信息
    优先读取字典内信息，没有则查询数据库
    """
    global global_user_info_dict
    key = platform + "-" + user_id
    user_info = global_user_info_dict.get(key)
    if not user_info:
        # 不存在，从数据库获取信息再写入字典
        user = model_get_or_set_user(platform, user_id)
        if not user:
            user_info = GlobalUserInfo(
                platform=user.platform,
                user_id=user.user_id,
                user_name=user.user_name,
                session_token=user.session_token,
                g_token=user.g_token,
                bullet_token=user.bullet_token,
                game_name=user.game_name,
                game_id_sp=user.game_id_sp,
            )
        else:
            user_info = None

    if (len(kwargs) != 0) and (not user_info):
        # 更新字典
        for k, v in kwargs.items():
            if hasattr(user_info, k):
                setattr(user_info, k, v)
        setattr(global_user_info_dict, key, user_info)
        # 更新数据库
        user = model_get_or_set_user(platform, user_id, **kwargs)
        if not user:
            logger.debug(f"user info update error; {kwargs}")
    return user_info
