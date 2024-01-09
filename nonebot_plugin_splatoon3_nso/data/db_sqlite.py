import copy
import datetime
import json
import os

import httpx
from httpx import Response
from loguru import logger
from sqlalchemy import Column, String, create_engine, Integer, Boolean, Text, DateTime, func, Float
from sqlalchemy.sql import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

dir_plugin = os.path.abspath(os.path.join(__file__, os.pardir))
database_uri_main = f'sqlite:///{dir_plugin}/resource/nso_data.sqlite'
database_uri_friends = f'sqlite:///{dir_plugin}/resource/data_friend.sqlite'

DIR_TEMP_IMAGE = f'{os.path.abspath(os.path.join(__file__, os.pardir))}/resource/temp_image'

Base_Main = declarative_base()
engine = create_engine(database_uri_main)
Base_Main.metadata.create_all(engine)
DBSession = sessionmaker(bind=engine)

Base_Friends = declarative_base()
engine_friends = create_engine(database_uri_friends)
Base_Friends.metadata.create_all(engine_friends)
DBSession_Friends = sessionmaker(bind=engine_friends)


# Table
class UserTable(Base_Main):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(), unique=True, nullable=True)
    user_id = Column(String(), unique=True, nullable=True)
    user_name = Column(String(), nullable=True)
    push_cnt = Column(Integer(), default=0)
    cmd_cnt = Column(Integer(), default=0)
    stat_key = Column(String(), nullable=True)
    session_token = Column(String(), nullable=True)  # 账号缓存凭证
    g_token = Column(String(), nullable=True)  # web service token，可能是游戏网页通用token
    bullet_token = Column(String(), nullable=True)  # 作用未知，可能是sp3应用专用token
    user_info = Column(Text(), nullable=True)
    game_name = Column(String(), default='')
    game_id_sp = Column(String(), nullable=True)
    api_notify = Column(Integer(), default=1)  # 0:close 1:open
    report_notify = Column(Integer(), default=1)  # 0:close 1:open
    last_play_time = Column(DateTime(), nullable=True)
    first_play_time = Column(DateTime(), nullable=True)
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


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
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


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
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


class Weapon(Base_Main):
    __tablename__ = 'weapon'

    id = Column(Integer, primary_key=True, autoincrement=True)
    weapon_id = Column(String(), default='')
    weapon_name = Column(String(), default='')
    image2d = Column(String(), default='')
    image2d_thumb = Column(String(), default='')
    image3d = Column(String(), default='')
    image3d_thumb = Column(String(), default='')
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


class TempImageTable(Base_Main):
    __tablename__ = 'temp_image'

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(), default='')
    name = Column(String(), default='')
    link = Column(String(), default='')
    file_name = Column(String(), default='')
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


class UserFriendTable(Base_Friends):
    __tablename__ = 'user_friend'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(), nullable=False)
    friend_id = Column(String(), nullable=False)
    player_name = Column(String(), default='')
    nickname = Column(String(), default='')
    game_name = Column(String(), default='')
    user_icon = Column(String(), default='')
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())
