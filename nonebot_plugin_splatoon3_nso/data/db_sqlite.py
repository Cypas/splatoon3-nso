import copy
import datetime
import json
import os

import httpx
from httpx import Response
from loguru import logger
from sqlalchemy import Column, String, create_engine, Integer, Boolean, Text, DateTime, func, Float, \
    PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.sql import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from ..utils import DIR_RESOURCE, get_time_now_china_str

database_uri_main = f'sqlite:///{DIR_RESOURCE}/nso_data.sqlite'
database_uri_friends = f'sqlite:///{DIR_RESOURCE}/data_friend.sqlite'

DIR_TEMP_IMAGE = f'{DIR_RESOURCE}/temp_image'

Base_Main = declarative_base()
engine = create_engine(database_uri_main)

Base_Friends = declarative_base()
engine_friends = create_engine(database_uri_friends)


# Table
class UserTable(Base_Main):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(), nullable=True)
    user_id = Column(String(), nullable=True)
    user_name = Column(String(), nullable=True)
    push_cnt = Column(Integer(), default=0)
    cmd_cnt = Column(Integer(), default=0)
    stat_key = Column(String(), nullable=True)
    session_token = Column(String(), nullable=True)  # 账号缓存凭证
    access_token = Column(String(), nullable=True)  # nso用户操作token |有效期2h| 获取ns friends，好友码
    g_token = Column(String(), nullable=True)  # web service token，nso内sp3网页服务token |有效期3h| nso页面操作，截图时使用
    bullet_token = Column(String(), nullable=True)  # nso内sp3网页api接口token |有效期2h| 战绩api接口使用
    user_info = Column(Text(), nullable=True)
    game_name = Column(String(), default='')
    game_sp_id = Column(String(), nullable=True)
    ns_name = Column(String(), nullable=True)
    ns_friend_code = Column(String(), nullable=True)
    api_notify = Column(Integer(), default=1)  # 0:close 1:open
    report_notify = Column(Integer(), default=1)  # 0:close 1:open
    last_play_time = Column(String(), nullable=True)
    first_play_time = Column(String(), nullable=True)
    create_time = Column(String(), default=get_time_now_china_str())
    update_time = Column(String(), onupdate=get_time_now_china_str())  # sqlalchemy自带的fun.now()会返回utc时间，而非本地时间，故弃用改为自定义函数


    __table_args__ = (
        UniqueConstraint("platform", "user_id", name='Idx_Platform_User'),
    )


class TopPlayer(Base_Main):
    __tablename__ = 'top_player'

    id = Column(Integer, primary_key=True, autoincrement=True)
    top_id = Column(String(), default='')
    top_type = Column(String(), default='')
    rank = Column(Integer(), default=0)
    power = Column(String(), default='')
    player_name = Column(String(), default='')
    player_name_id = Column(String(), default='')
    player_code = Column(String(), default='')
    byname = Column(String(), default='')
    weapon_id = Column(Integer(), default=0)
    weapon = Column(String(), default='')
    play_time = Column(DateTime())
    create_time = Column(String(), default=get_time_now_china_str())
    update_time = Column(String(), onupdate=get_time_now_china_str())  # sqlalchemy自带的fun.now()会返回utc时间，而非本地时间，故弃用改为自定义函数


class TopAll(Base_Main):
    __tablename__ = 'top_all'

    id = Column(Integer, primary_key=True, autoincrement=True)
    top_id = Column(String(), default='')
    top_type = Column(String(), default='')
    rank = Column(Integer(), default=0)
    power = Column(String(), default='')
    player_name = Column(String(), default='')
    player_name_id = Column(String(), default='')
    player_code = Column(String(), default='', index=True)
    byname = Column(String(), default='')
    weapon_id = Column(Integer(), default=0)
    weapon = Column(String(), default='')
    play_time = Column(DateTime())
    create_time = Column(String(), default=get_time_now_china_str())
    update_time = Column(String(), onupdate=get_time_now_china_str())  # sqlalchemy自带的fun.now()会返回utc时间，而非本地时间，故弃用改为自定义函数


# class Weapon(Base_Main):
#     __tablename__ = 'weapon'
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     weapon_id = Column(String(), default='')
#     weapon_name = Column(String(), default='')
#     image2d = Column(String(), default='')
#     image2d_thumb = Column(String(), default='')
#     image3d = Column(String(), default='')
#     image3d_thumb = Column(String(), default='')
#     create_time = Column(String(), default=get_time_now_china_str())
#     update_time = Column(String(), onupdate=get_time_now_china_str())  # sqlalchemy自带的fun.now()会返回utc时间，而非本地时间，故弃用改为自定义函数


class TempImageTable(Base_Main):
    __tablename__ = 'temp_image'

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(), default='')
    name = Column(String(), default='')
    link = Column(String(), default='')
    file_name = Column(String(), default='')
    create_time = Column(String(), default=get_time_now_china_str())
    update_time = Column(String(), onupdate=get_time_now_china_str())  # sqlalchemy自带的fun.now()会返回utc时间，而非本地时间，故弃用改为自定义函数

    __table_args__ = (
        UniqueConstraint("type", "name", name='Idx_Type_Name'),
    )


class UserFriendTable(Base_Friends):
    __tablename__ = 'user_friend'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(), nullable=False)
    friend_id = Column(String(), nullable=False)
    player_name = Column(String(), default='')
    nickname = Column(String(), default='')
    game_name = Column(String(), default='')
    user_icon = Column(String(), default='')
    create_time = Column(String(), default=get_time_now_china_str())
    update_time = Column(String(), onupdate=get_time_now_china_str())  # sqlalchemy自带的fun.now()会返回utc时间，而非本地时间，故弃用改为自定义函数


Base_Main.metadata.create_all(engine)
DBSession = sessionmaker(bind=engine)
Base_Friends.metadata.create_all(engine_friends)
DBSession_Friends = sessionmaker(bind=engine_friends)