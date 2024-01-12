from typing import List, Union

from nonebot import get_driver
from pydantic import BaseModel, validator


# 其他地方出现的类似 from .. import config，均是从 __init__.py 导入的 Config 实例
class Config(BaseModel):
    # 默认 proxy = None 表示不使用代理进行连接
    splatoon3_proxy_address: str = ""
    # 指定回复模式，开启后将通过触发词的消息进行回复
    splatoon3_reply_mode: bool = False
    # 日志消息将由该bot发送至tg频道
    splatoon3_notify_tg_bot_id: str = ""
    splatoon3_tg_channel_msg_chat_id: str = ""
    splatoon3_tg_channel_job_chat_id: str = ""
    # 日志消息将由该bot发送至kook频道
    splatoon3_notify_kk_bot_id: str = ""
    splatoon3_kk_channel_msg_chat_id: str = ""
    splatoon3_kk_channel_job_chat_id: str = ""
    # deno_path  需要先在linux下安装deno，参考https://www.denojs.cn/ 此处填写安装路径
    splatoon3_deno_path: str = ""

    # 定时任务执行bot的id(必须配置)
    splatoon3_cron_job_execute_bot_id: str = ""
    # Q群无法登陆时其他平台的服务器id
    splatoon3_kk_guild_id: str = ""
    # bot上线，掉线时通知到频道
    splatoon3_bot_disconnect_notify: bool = True
    # 日程插件优先模式(主要影响帮助菜单，该配置项与nso查询插件公用)
    splatoon3_schedule_plugin_priority_mode: bool = False


driver = get_driver()
global_config = driver.config
plugin_config = Config.parse_obj(global_config)

# driver = None
# global_config = None
# plugin_config = Config()