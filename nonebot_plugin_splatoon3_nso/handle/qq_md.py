from collections import defaultdict

from nonebot.adapters.qq.models import MessageKeyboard, MessageMarkdown
from nonebot.adapters.telegram.model import InlineKeyboardMarkup

from ..config import plugin_config
from ..data.utils import plugin_data, get_or_set_plugin_data
from ..utils.bot import *
from ..utils.keyboard import qq_build_keyboard, qq_build_markdown


async def nso_general_md(user_id, image_size: tuple, url: str, text_start: str = "", text_end: str = "") -> QQ_Msg:
    """为nso_通用查询拼装md结构"""
    image_width, image_height = image_size
    if text_start:
        text_start = md_text_replace(text_start)
    else:
        text_start = "发送/nso帮助查看详细用法"
    text_notice = await get_or_set_plugin_data("splatoon3_bot_notice")
    # 公告消息 作为 text_end
    if text_notice:
        text_end = "公告消息:" + md_text_replace(text_notice)
    else:
        if text_end:
            # 公告消息不存在时允许输出自定义文本
            text_end = md_text_replace(text_end)

    md_content = ""
    if user_id:
        md_content += "{at_user_id} "
    md_content += """{text_start}
![{img_size}]({img_url})
> {text_end}
"""

    params = {"text_start": f"{text_start}",
              "img_size": f"img#{image_width}px #{image_height}px",
              "img_url": f"{url}"
              }
    if user_id:
        params["at_user_id"] = f"<@{user_id}>"

    if text_end:
        params["text_end"] = md_text_replace(text_end)

    buttons = [[{"text": "查对战或打工", "data": "/last", "style": 1}, {"text": "查上局配装", "data": "/last b e"},
                {"text": "配装推荐", "data": "/配装"}],
               [{"text": "我的喷3", "data": "/me"}, {"text": "日报数据", "data": "/report"},
                {"text": "更多指令", "data": "/更多nso指令", "style": 1}],
               ]

    return build_markdown(md_content, params, buttons)


async def login_md(user_id, check_session=False) -> QQ_Msg:
    """无法使用login时转kook登录的md卡片提示"""
    keyboard_template_type = "kook_url"
    data1 = ""
    if check_session:
        # 使用其他功能前的检查
        data1 += "nso未登录，无法使用相关查询，"
    data1 += "QQ平台当前无法完成登录流程，请至其他平台完成登录后使用 /getlc 命令获取绑定码"
    data2 = f"Kook服务器id：{plugin_config.splatoon3_kk_guild_id}"
    data3 = ""
    if check_session:
        if user_id:
            title = f"<@{user_id}> 该功能需要登陆后才可使用"
        else:
            title = f"该功能需要登陆后才可使用"
    else:
        title = f"当前平台无法登录"

    return await text_msg_md(user_id=user_id, title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def push_md(user_id) -> QQ_Msg:
    """提示用户开启主动推送权限后才能用push"""
    keyboard_template_type = ""
    data1 = "QQ平台push现在仅可在开启了主动推送的Q群内使用"
    data2 = f"建议可以将小鱿鱿与自己创建一个2人小群，再开启主动推送权限"
    data3 = f"开启主动推送权限的方法请在新的小群内发送 /免艾特申请"
    title = f"请开启主动推送权限后再试"

    return await text_msg_md(user_id=user_id, title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def more_nso_help_md(user_id) -> QQ_Msg:
    """nso帮助的二级md按钮菜单"""
    keyboard_template_type = "more_nso_help"
    data1 = f"nso相关查询功能太多"
    data2 = f"若需要查看详细的命令用法"
    data3 = f"请点击最下面 nso查询详细用法 按钮"
    title = f"以下是更多常用nso命令"

    return await text_msg_md(user_id=user_id, title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def report_md(user_id, title, msg) -> QQ_Msg:
    """日报md菜单，将日报文本展示在文本md中，按钮使用nso通用按钮组"""
    keyboard_template_type = "nso_general"
    data1 = f"{msg}"
    data2 = f""
    data3 = f""

    return await text_msg_md(user_id=user_id, title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def new_user_added_md(user_id, title, msg) -> QQ_Msg:
    """被新用户添加时的md"""
    keyboard_template_type = "schedule"
    data1 = f"{msg}"
    data2 = f""
    data3 = f""
    title = f"{title}"

    return await text_msg_md(user_id=user_id, title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def admin_help_md(user_id) -> QQ_Msg:
    """nso帮助的md"""
    keyboard_template_type = "admin_help"
    data1 = f"部分指令需要加参数"
    data2 = "set_bot_notice {公告消息} 设置公告消息\ncopy_token {user_id} 复制token\nadd_black_msg_id {msg_id}添加黑名单\ndel_black_msg_id {msg_id}删除黑名单\n"
    data3 = f""
    title = f"管理员帮助菜单"

    return await text_msg_md(user_id=user_id, title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def text_msg_md(user_id: str = "", title: str = "", data1: str = "", data2: str = "", data3: str = "",
                      keyboard_template_type="") -> QQ_Msg:
    """
    通用的 文本引用消息md模版
    可提供 titile  title模版前面是引号开头
    引用文本  data1，data2，data3  这三个也支持\n进行换行   至少需要提供一个data1 data2和data3可以不给
    按钮模版类型 若不提供则没有按钮
    """
    # 固定的文本模版id
    md_content = ""
    if user_id:
        md_content += "{at_user_id} "
    md_content += """{title}
> {data1}
> {data2}
> {data3}
"""

    params = {"title": md_text_replace(title), "data1": md_text_replace(data1),
              "data2": md_text_replace(data2), "data3": md_text_replace(data3),
              }
    if user_id:
        params["at_user_id"] = f"<@{user_id}>"

    buttons = None
    if keyboard_template_type == "kook_url":
        # kook 服务器的链接 按钮模版
        buttons = [[{"text": "kook服务器", "link": "https://www.kookapp.cn/app/invite/mkjIOn"}]
                   ]
    if keyboard_template_type == "more_nso_help":
        # 更多nso指令 按钮模版
        buttons = [[{"text": "查上榜记录", "data": "/top"}, {"text": "最近开放战绩", "data": "/history o"},
                    {"text": "最近活动战绩", "data": "/history e"}],
                   [{"text": "ns好友状态", "data": "/nsfr"}, {"text": "ns好友码", "data": "/friend_code"},
                    {"text": "ns头像", "data": "/my_icon"}],
                   [{"text": "喷三好友状态", "data": "/friends"}, {"text": "观星导出", "data": "/观星导出"},
                    {"text": "nso网页版", "data": "/nso_web"}],
                   [{"text": "小鱿鱿官方群",
                     "link": "http://qm.qq.com/cgi-bin/qm/qr?_wv=1027&k=zGefDQ4GQYFPAB-hFkeFLlyQ8qbG5S2w&authKey=j0b9yXmtSzYry6qQQ%2FFXxw7U%2Fp6kXyET0xj%2BRHWxeRa20zvJeN8W91noNrJDmDyO&noverify=0&group_code=827977720",
                     "style": 1},
                    {"text": "nso查询详细用法", "data": "/nso帮助"}
                    ]
                   ]
    if keyboard_template_type == "nso_general":
        # 也使用nso通用的 按钮模版
        buttons = [[{"text": "查对战或打工", "data": "/last"}, {"text": "查上局配装", "data": "/last b e"},
                    {"text": "配装推荐", "data": "/配装"}],
                   [{"text": "我的喷3", "data": "/me"}, {"text": "日报数据", "data": "/report"},
                    {"text": "更多指令", "data": "/更多nso指令"}],
                   ]
    if keyboard_template_type == "schedule":
        # 日程按钮 模版
        buttons = [[{"text": "图图", "data": "/图图"}, {"text": "开放", "data": "/012开放", "style": 1},
                    {"text": "活动", "data": "/活动"}, {"text": "打工", "data": "/全部工"}],
                   [{"text": "配装推荐", "data": "/配装"}, {"text": "随机武器", "data": "/随机武器"}],
                   [{"text": "ns好友状态", "data": "/nsfr"}, {"text": "查对战或打工战绩", "data": "/last"},
                    {"text": "日程查询详细用法", "data": "/帮助"}]
                   ]
    if keyboard_template_type == "admin_help":
        # 日程按钮 模版
        buttons = [
            [{"text": "get_push", "data": "/admin get_push"}, {"text": "close_push", "data": "/admin close_push"},
             {"text": "设置公告", "data": "/admin set_bot_notice"}, {"text": "运行状态", "data": "/admin status"}],
            [{"text": "加黑名单", "data": "/admin add_black_msg_id"},
             {"text": "删黑名单", "data": "/admin del_black_msg_id"},
             {"text": "复制token", "data": "/admin copy_token"}, {"text": "还原token", "data": "/admin restore_token"}],
            [{"text": "写x赛", "data": "/admin get_x_player"}, {"text": "写活动", "data": "/admin get_event_top"},
             {"text": "写日报", "data": "/admin set_report"},
             {"text": "写好友", "data": "/admin get_user_friends"},{"text": "同步stat", "data": "/admin sync_stat_ink"}],
        ]

    return build_markdown(md_content, params, buttons)


async def full_message_check_md(image_size: tuple, img_url: str, check_url: str) -> QQ_Msg:
    """发送全量消息授权的url确认链接"""
    image_width, image_height = image_size
    md_content = """{text_start}
{text_bold}

![{img_size}]({img_url})
"""
    params = {"text_start": "请群主点击小鱿鱿头像，按照下图说明授予接收全部消息和主动消息的权限",
              "text_bold": "需要QQ版本(9.2.90版本及以上)",
              "img_size": f"img#{image_width}px #{image_height}px",
              "img_url": f"{img_url}"
              }

    # 作废，不再需要链接
    # buttons = [[{"text": "群主大大请点击这里同意申请", "url": check_url}]]

    return build_markdown(md_content, params)


async def get_qq_face_md(user_id: str, url: str, w: int = 0, h: int = 0) -> QQ_Msg:
    """转发表情用md结构"""
    if not w or not h:
        image_width, image_height = (500, 500)
    else:
        image_width, image_height = (w, h)

    md_content = ""
    if user_id:
        md_content += "{at_user_id} "
    md_content += """{text_start}
![{img_size}]({img_url})
"""
    params = {"text_start": "qq表情包导出成功，下面图片点开可保存至手机",
              "img_size": f"img#{image_width}px #{image_height}px",
              "img_url": f"{url}"
              }
    if user_id:
        params["at_user_id"] = f"<@{user_id}>"

    return build_markdown(md_content, params)


def build_markdown(md_content, params, buttons=None) -> QQ_Msg:
    """
    自定义md构建器，返回适配器能直接使用的md消息结构体
    :param md_content: 模板字符串
    :param params: 字典，模板字符串中的占位符
    :param buttons: 按钮列表，每个元素为按钮字典
    """
    md = qq_build_markdown(md_content, params)

    msg = [QQ_MsgSeg.markdown(md)]
    if buttons:
        keyboard = qq_build_keyboard(buttons)
        msg.append(QQ_MsgSeg.keyboard(keyboard))
    return QQ_Msg(msg)


def md_text_replace(text: str):
    return text.replace("\\n", "\r").replace("\n", "\r").replace("\\r", "\r")


async def c2c_login_md(login_url) -> QQ_Msg:
    """c2c login 自定义卡片  需要原生md权限，已无法使用"""
    template_id = "102083290_1705923685"
    docs_url = "https://docs.qq.com/doc/DSVlLSnloTGZqTmNz"

    title = "nso登录"
    content = "详细nso登录步骤可查询下面文档教程\r！！！\r打开nso登录地址后不要用QQ内置浏览器，点右上角三个点，然后用系统浏览器打开\r！！！"
    docs_url_title = "小鱿鱿使用文档及教程"
    login_url_title = "点我打开nso登录网页"
    params = [{"key": "title", "values": [f"{title}"]}]
    params.extend([{"key": "data1", "values": [f"{content}"]}])

    md = MessageMarkdown.model_validate({
        "custom_template_id": f"{template_id}",
        "params": params
    })
    keyboard = MessageKeyboard.model_validate({
        "content": {
            "rows": [{"buttons": [
                {
                    "id": "1",
                    "render_data": {
                        "label": f"{docs_url_title}",
                        "visited_label": f"{docs_url_title}",
                        "style": 0
                    },
                    "action": {
                        "type": 0,
                        "permission": {
                            "type": 2,
                        },
                        "unsupport_tips": "客户端不支持",
                        "data": f"{docs_url}",
                    }
                }

            ]},
                {"buttons": [
                    {
                        "id": "1",
                        "render_data": {
                            "label": f"{login_url_title}",
                            "visited_label": f"{login_url_title}",
                            "style": 0
                        },
                        "action": {
                            "type": 0,
                            "permission": {
                                "type": 2,
                            },
                            "unsupport_tips": "客户端不支持",
                            "data": f"{login_url}",
                        }
                    }

                ]},
            ]
        }
    })
    qq_msg = QQ_Msg([QQ_MsgSeg.markdown(md), QQ_MsgSeg.keyboard(keyboard)])
    return qq_msg


async def url_md(title, content, url_title, url) -> QQ_Msg:
    """仅发一个url的按钮卡片  需要原生md权限，已无法使用"""
    template_id = "102083290_1705923685"
    if not title:
        title = " "
    params = [{"key": "title", "values": [f"{title}"]}]
    params.extend([{"key": "data1", "values": [f"{content}"]}])

    md = MessageMarkdown.model_validate({
        "custom_template_id": f"{template_id}",
        "params": params
    })
    keyboard = MessageKeyboard.model_validate({
        "content": {
            "rows": [{"buttons": [
                {
                    "id": "1",
                    "render_data": {
                        "label": f"{url_title}",
                        "visited_label": f"{url_title}",
                        "style": 0
                    },
                    "action": {
                        "type": 0,
                        "permission": {
                            "type": 2,
                        },
                        "unsupport_tips": "客户端不支持",
                        "data": f"{url}",
                    }
                }

            ]},
            ]
        }
    })
    qq_msg = QQ_Msg([QQ_MsgSeg.markdown(md), QQ_MsgSeg.keyboard(keyboard)])
    return qq_msg
