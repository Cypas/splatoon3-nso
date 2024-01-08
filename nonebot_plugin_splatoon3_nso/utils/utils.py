import os

BOT_VERSION = '1.5.6'
DIR_RESOURCE = f'{os.path.abspath(os.path.join(__file__, os.pardir))}/resource'
GLOBAL_LOGIN_STATUS_DICT: dict = {}

def multiple_replace(text, _dict):
    """批量替换文本"""
    for key in _dict:
        text = text.replace(key, _dict[key])
    return text


def init_path(path_folder):
    """初始化文件夹路径"""
    if not os.path.exists(path_folder):
        os.mkdir(path_folder)

