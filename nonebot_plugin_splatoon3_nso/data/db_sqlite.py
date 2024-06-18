from sqlalchemy import Column, String, create_engine, Integer, Text, DateTime, func, Float, \
    UniqueConstraint
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from ..utils import DIR_RESOURCE

database_uri_main = f"sqlite:///{DIR_RESOURCE}/nso_data.sqlite"
database_uri_friends = f"sqlite:///{DIR_RESOURCE}/data_friend.sqlite"

DIR_TEMP_IMAGE = f"{DIR_RESOURCE}/temp_image"

Base_Main = declarative_base()
engine = create_engine(database_uri_main)  # 加上, echo=True可以输出sql语句

Base_Friends = declarative_base()
engine_friends = create_engine(database_uri_friends)


# Table
class UserTable(Base_Main):
    __tablename__ = "user"

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
    user_info = Column(Text(), nullable=True)  # 当前版本未使用字段
    user_agreement = Column(Integer(), default=0)  # 用户协议，用户是否已知晓可能导致nso被封的情况
    game_name = Column(String(), default="")
    game_sp_id = Column(String(), nullable=True, index=True)
    ns_name = Column(String(), nullable=True)
    ns_friend_code = Column(String(), nullable=True)
    stat_notify = Column(Integer(), default=1)  # 0:close 1:open
    report_notify = Column(Integer(), default=1)  # 0:close 1:open
    last_play_time = Column(String(), nullable=True)
    first_play_time = Column(String(), nullable=True)
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("platform", "user_id", name="Idx_Platform_User"),
    )


class TopPlayer(Base_Main):
    __tablename__ = "top_player"

    id = Column(Integer, primary_key=True, autoincrement=True)
    top_id = Column(String(), default="")
    top_type = Column(String(), default="")
    rank = Column(Integer(), default=0)
    power = Column(String(), default="")
    player_name = Column(String(), default="")
    player_name_id = Column(String(), default="")
    player_code = Column(String(), default="", index=True)
    byname = Column(String(), default="")
    weapon_id = Column(Integer(), default=0)
    weapon = Column(String(), default="")
    play_time = Column(DateTime())
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


class TopAll(Base_Main):
    __tablename__ = "top_all"

    id = Column(Integer, primary_key=True, autoincrement=True)
    top_id = Column(String(), default="")
    top_type = Column(String(), default="")
    rank = Column(Integer(), default=0)
    power = Column(String(), default="")
    player_name = Column(String(), default="")
    player_name_id = Column(String(), default="")
    player_code = Column(String(), default="", index=True)
    byname = Column(String(), default="")
    weapon_id = Column(Integer(), default=0)
    weapon = Column(String(), default="")
    play_time = Column(DateTime())
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


class TempImageTable(Base_Main):
    __tablename__ = "temp_image"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(), default="")
    name = Column(String(), default="")
    link = Column(String(), default="")
    file_name = Column(String(), default="")
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("type", "name", name="Idx_Type_Name"),
    )


class Report(Base_Main):
    __tablename__ = "report"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(), nullable=False)
    user_id_sp = Column(String(), default="", index=True)
    nickname = Column(String(), default="")
    name_id = Column(String(), default="")
    byname = Column(String(), default="")
    rank = Column(Integer, default="")
    udemae = Column(String(), default="")
    udemae_max = Column(String(), default="")
    total_cnt = Column(Integer, default="")
    win_cnt = Column(Integer, default="")
    lose_cnt = Column(Integer, default="")
    win_rate = Column(Float, default=None)
    paint = Column(Integer, default="")
    badges = Column(Integer, default="")
    event_gold = Column(Integer, default="")
    event_silver = Column(Integer, default="")
    event_bronze = Column(Integer, default="")
    event_none = Column(Integer, default="")
    open_gold = Column(Integer, default="")
    open_silver = Column(Integer, default="")
    open_bronze = Column(Integer, default="")
    open_none = Column(Integer, default="")
    max_power = Column(Float, default=None)
    x_ar = Column(Float, default=None)
    x_lf = Column(Float, default=None)
    x_gl = Column(Float, default=None)
    x_cl = Column(Float, default=None)
    coop_cnt = Column(Integer, default="")
    coop_gold_egg = Column(Integer, default="")
    coop_egg = Column(Integer, default="")
    coop_boss_cnt = Column(Integer, default="")
    coop_rescue = Column(Integer, default="")
    coop_point = Column(Integer, default="")
    coop_gold = Column(Integer, default="")
    coop_silver = Column(Integer, default="")
    coop_bronze = Column(Integer, default="")
    last_play_time = Column(DateTime(), nullable=True)
    create_time = Column(DateTime(), default=func.now())


class UserFriendTable(Base_Friends):
    __tablename__ = "user_friend"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(), nullable=False)
    friend_id = Column(String(), nullable=False)
    player_name = Column(String(), default="", index=True)
    nickname = Column(String(), default="")
    game_name = Column(String(), default="")
    user_icon = Column(String(), default="")
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


DBSession = sessionmaker()
DBSession_Friends = sessionmaker()
# DBSession = sessionmaker(bind=engine)
# DBSession_Friends = sessionmaker(bind=engine_friends)


def init_db():
    """初始化数据库"""
    global DBSession
    global DBSession_Friends
    Base_Main.metadata.create_all(engine)
    DBSession.configure(bind=engine)
    Base_Friends.metadata.create_all(engine_friends)
    DBSession_Friends.configure(bind=engine_friends)
