from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel


# 其他地方出现的类似 from .. import config，均是从 __init__.py 导入的 Config 实例
class Config(BaseModel):
    # 默认 proxy = "" 表示不使用代理进行连接
    splatoon3_proxy_address: str = ""
    # 局部域名代理模式,具体依据服务器对各个域名访问情况进行设置，默认True，False情况为全部域名请求代理
    splatoon3_proxy_list_mode: bool = True
    # 局部域名代理列表
    # 插件内全部请求的域名有:
    # github.com   此项无法添加到局域代理列表 git命令会访问，如果存在splatoon3_proxy_address配置项，强制要求走代理路径
    # api.imink.app  模拟nso授权步骤的公开接口，项目地址 https://github.com/imink-app/f-API
    # nxapi-znca-api.fancy.org.uk  模拟nso授权步骤的公开接口2，项目地址 https://github.com/samuelthomas2774/nxapi-znca-api
    # apps.apple.com
    # accounts.nintendo.com
    # api.accounts.nintendo.com
    # api-lp1.znc.srv.nintendo.net
    # api.lp1.av5ja.srv.nintendo.net  鱿鱼圈域名，国内服务器一般都能直连，不需要代理
    splatoon3_proxy_list: list = ["accounts.nintendo.com", "api.accounts.nintendo.com", "api-lp1.znc.srv.nintendo.net"]
    # 指定回复模式，开启后将通过触发词的消息进行回复
    splatoon3_reply_mode: bool = False
    # 日志消息将由该bot发送至tg频道
    splatoon3_notify_tg_bot_id: str | int = ""
    splatoon3_tg_channel_msg_chat_id: str | int = ""
    splatoon3_tg_channel_job_chat_id: str | int = ""
    # 日志消息将由该bot发送至kook频道
    splatoon3_notify_kk_bot_id: str | int = ""
    splatoon3_kk_channel_msg_chat_id: str | int = ""
    splatoon3_kk_channel_job_chat_id: str | int = ""
    # deno_path  需要先在系统下安装deno，参考https://www.denojs.cn/ 此处填写安装路径，具体到deno文件，如"/home/ubuntu/.deno/bin/deno"
    splatoon3_deno_path: str = ""

    # Q群在进行登录时，将用户引导至kook平台完成登录的服务器id
    splatoon3_kk_guild_id: str | int = ""
    # bot上线，掉线时通知到频道
    splatoon3_bot_disconnect_notify: bool = True
    # 日程插件的帮助菜单优先模式(会影响帮助菜单由哪个插件提供，该配置项与日程查询插件公用)
    splatoon3_schedule_plugin_priority_mode: bool = False
    # 部分消息使用qq平台md卡片,开启了也没用，md模版需要在qqbot端进行审核，模板id目前在代码里是写死的
    splatoon3_qq_md_mode: bool = False
    # 没有匹配命令时是否兜底回复
    splatoon3_unknown_command_fallback_reply: bool = True
    # 兜底回复kook服务器黑名单列表   如["4498783094960820"]
    splatoon3_unknown_command_fallback_reply_kook_black_list: list = []


driver = get_driver()
global_config = driver.config
plugin_config = get_plugin_config(Config)
