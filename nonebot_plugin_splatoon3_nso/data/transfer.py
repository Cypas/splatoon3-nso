import shutil
from typing import Type

from sqlalchemy import Column, String, create_engine, Integer, Boolean, Text, DateTime, func
from sqlalchemy.sql import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from .db_sqlite import database_uri_main, init_db, DBSession, UserTable
from ..utils import DIR_RESOURCE

database_uri_old_user = f"sqlite:///{DIR_RESOURCE}/data.sqlite"
Base_Old_user = declarative_base()
engine_old_user = create_engine(database_uri_old_user)


class oldUserTable(Base_Old_user):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id_tg = Column(String(), unique=True, nullable=True)
    user_id_qq = Column(String(), unique=True, nullable=True)
    user_id_wx = Column(String(), unique=True, nullable=True)
    user_id_kk = Column(String(), unique=True, nullable=True)
    user_id_bind = Column(String(), unique=True, nullable=True)
    username = Column(String(), nullable=True)
    first_name = Column(String(), nullable=True)
    last_name = Column(String(), nullable=True)
    push = Column(Boolean(), default=False)
    push_cnt = Column(Integer(), default=0)
    cmd_cnt = Column(Integer(), default=0)
    map_cnt = Column(Integer(), default=0)
    api_key = Column(String(), nullable=True)
    api_notify = Column(Integer(), default=1)
    acc_loc = Column(String(), nullable=True)
    session_token = Column(String(), nullable=True)
    session_token_2 = Column(String(), nullable=True)
    gtoken = Column(String(), nullable=True)
    bullettoken = Column(String(), nullable=True)
    user_info = Column(Text(), nullable=True)
    cmd = Column(Text(), nullable=True)
    nickname = Column(String(), default="")
    user_id_sp = Column(String(), nullable=True)
    report_type = Column(Integer(), default=0)  # 1:daily, 2:weekly, 3:monthly, 4:season
    last_play_time = Column(DateTime(), nullable=True)
    first_play_time = Column(DateTime(), nullable=True)
    create_time = Column(DateTime(), default=func.now())
    update_time = Column(DateTime(), onupdate=func.now())


DBSession_Old_User = sessionmaker()


def init_old_user_db():
    """初始化旧用户数据库"""
    global DBSession_Old_User
    DBSession_Old_User.configure(bind=engine_old_user)


def transfer_user_db():
    """转移旧版本用户数据"""
    # 复制旧数据库文件
    old_db_path = f"{DIR_RESOURCE}/data.sqlite"
    new_db_path = f"{DIR_RESOURCE}/nso_data.sqlite"
    shutil.copy(old_db_path, new_db_path)
    # 连接新数据库删除user表
    engine = create_engine(database_uri_main)
    conn = engine.connect()
    conn.execute(text("drop table 'user'"))
    conn.close()
    # 创建新结构
    init_db()
    init_old_user_db()
    # 旧表添加唯一约数   索引index会自动更新，无需管
    # sql lite 在表创建后，无法更改约束，先放弃

    # 创建双方会话对象
    session = DBSession()
    old_session = DBSession_Old_User()
    # 读取全部session_token不为空的旧用户
    list_users: list[Type[oldUserTable]] = old_session.query(oldUserTable).filter(
        oldUserTable.session_token.isnot(None)).all()
    _pool = 100
    new_list_u: list = []
    for i in range(0, len(list_users), _pool):
        pool_list_users: list[oldUserTable] = list_users[i:i + _pool]
        for old_u in pool_list_users:
            # new_u = UserTable()
            # 不继承id
            # new_u.id = old_u.id

            platform = ""
            user_id = ""
            if old_u.user_id_tg:
                platform = "Telegram"
                user_id = old_u.user_id_tg
            elif old_u.user_id_qq:
                if old_u.user_id_qq.isdigit():
                    # 纯数字 v11协议
                    platform = "OneBot V11"
                else:
                    platform = "QQ"
                user_id = old_u.user_id_qq
            elif old_u.user_id_wx:
                platform = "OneBot V12"
                user_id = old_u.user_id_wx
            elif old_u.user_id_kk:
                platform = "Kaiheila"
                user_id = old_u.user_id_kk

            new_u = {"platform": platform,
                     "user_id": user_id,
                     "user_name": old_u.username,
                     "push_cnt": old_u.push_cnt,
                     "cmd_cnt": old_u.cmd_cnt,
                     "stat_key": old_u.api_key,
                     "session_token": old_u.session_token,
                     "game_name": old_u.nickname,
                     "game_sp_id": old_u.user_id_sp,
                     "stat_notify": old_u.api_notify or 1,
                     "report_notify": old_u.report_type or 1,
                     "create_time": old_u.create_time,
                     }

            new_list_u.append(new_u)

        # 插入100条数据
        session.bulk_insert_mappings(UserTable, new_list_u)
        session.commit()
        new_list_u.clear()
    session.close()
    old_session.close()
