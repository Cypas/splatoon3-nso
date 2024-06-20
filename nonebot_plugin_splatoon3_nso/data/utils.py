import copy

from sqlalchemy import text

from .db_sqlite import DBSession, TempImageTable, DIR_TEMP_IMAGE
from ..utils import init_path, get_file_url


class GlobalUserInfo:
    """全局公用用户类"""

    def __init__(self, **kwargs):
        self.db_id = kwargs.get('db_id', None)
        self.platform = kwargs.get('platform', None)
        self.user_id = kwargs.get('user_id', None)
        self.user_name = kwargs.get('user_name', None)
        self.session_token = kwargs.get('session_token', None)
        self.g_token = kwargs.get('g_token', None)
        self.bullet_token = kwargs.get('bullet_token', None)
        self.access_token = kwargs.get('access_token', None)
        self.game_name = kwargs.get('game_name', None)
        self.game_sp_id = kwargs.get('game_sp_id', None)
        self.push = kwargs.get('push', 0)
        self.push_cnt = kwargs.get('push_cnt', 0)
        self.cmd_cnt = kwargs.get('cmd_cnt', 0)
        self.user_agreement = kwargs.get('user_agreement', 0)
        self.stat_key = kwargs.get('stat_key', None)
        self.ns_name = kwargs.get('ns_name', None)
        self.ns_friend_code = kwargs.get('ns_friend_code', None)
        self.req_client = kwargs.get('req_client', None)


async def model_get_or_set_temp_image(_type, name: str, link=None) -> TempImageTable:
    """获取或设置缓存图片"""
    session = DBSession()
    name = name.replace("/", "-")
    row: TempImageTable = get_insert_or_update_obj(TempImageTable, {"type": _type, "name": name})

    download_flag: bool = False
    temp_image = TempImageTable()
    if row:
        # 判断是否是用户图像缓存，并比对缓存数据是否需要更新, 图片名称是否为空
        if (link and row.type in (
                "friend_icon", 'ns_friend_icon', 'my_icon') and row.link != link) or not row.file_name:
            download_flag = True
        else:
            temp_image = row
    else:
        download_flag = True
    if download_flag and link:
        # 通过url下载图片储存至本地
        image_data = await get_file_url(link)
        file_name = ""
        # 1024 bytes长度 = 1k
        lens = len(image_data)
        if lens > 200:
            # 创建文件夹
            init_path(f"{DIR_TEMP_IMAGE}")
            init_path(f"{DIR_TEMP_IMAGE}/{_type}")

            file_name = f"{name}.png"
            with open(f"{DIR_TEMP_IMAGE}/{_type}/{file_name}", "wb") as f:
                f.write(image_data)
        temp_image = get_insert_or_update_obj(TempImageTable, {"type": _type, "name": name}, type=_type, name=name,
                                              link=link,
                                              file_name=file_name)

        # 将复制值传给orm,session提交后，获取的数据会失效，无法作为值进行返回，这里必须深度复制
        session.add(copy.deepcopy(temp_image))
    session.commit()
    session.close()
    return temp_image


def get_insert_or_update_obj(cls, filter_dict, **kw):
    """ 获取插入或更新对象
    cls:            Model 类名
    filter_dict:      filter的参数.eg:{"name"="嘤嘤嘤"}
    **kw:           【属性、值】字典,用于构建新实例，或修改存在的记录
    """
    session = DBSession()
    query = session.query(cls)
    # 拼装全部筛选条件
    if len(filter_dict) > 0:
        for k, v in filter_dict.items():
            query = query.filter(text(str(k) + "='" + str(v) + "'"))
            # query.filter_by()
        row = query.first()
    else:
        # 没有提供筛选
        row = None
    if not row and len(kw) > 0:
        # 创建新对象
        res = cls()
    else:
        res = row

    for k, v in kw.items():
        if hasattr(res, k):
            setattr(res, k, v)
    session.close()
    return res
