import re

from nonebot.adapters.qq.models import MessageKeyboard, MessageMarkdown
from nonebot.adapters.telegram.model import InlineKeyboardMarkup

from ..config import plugin_config
from ..data.utils import plugin_data, get_or_set_plugin_data
from ..utils.bot import *


async def nso_general_md(user_id, image_size: tuple, url: str, text_start: str = "", text_end: str = "") -> QQ_Msg:
    """为nso_通用查询拼装md结构"""
    template_id = "102083290_1705920931"
    keyboard_template_id = "102083290_1772274396"
    image_width, image_height = image_size
    if text_start:
        text_start = md_text_replace(text_start)
    else:
        text_start = "发送/nso帮助查看详细用法"
    text_notice = await get_or_set_plugin_data("splatoon3_bot_notice")
    # 公告消息 作为 text_end
    if text_notice:
        text_end = md_text_replace(text_notice)
    else:
        if text_end:
            # 公告消息不存在时允许输出自定义文本
            text_end = md_text_replace(text_end)

    # 如果kv值为空，那只能不传，空值似乎最多只允许一个
    params = []
    if user_id:
        params.append({"key": "at_user_id", "values": [f"<@{user_id}>"]})
    params.extend([{"key": "text_start", "values": [f"{text_start}"]},
                   {"key": "img_size", "values": [f"img#{image_width}px #{image_height}px"]},
                   {"key": "img_url", "values": [f"{url}"]}])
    if text_end:
        text_end = "\r" + md_text_replace(text_end)
        params.append({"key": "text_end", "values": [f"{text_end}"]})
    md = MessageMarkdown.model_validate({
        "custom_template_id": f"{template_id}",
        "params": params
    })

    # 完整kv对
    # md = MessageMarkdown.model_validate({
    #     "custom_template_id": f"{template_id}",
    #     "params": [{"key": "at_user_id", "values": [f"<@{user_id}>"]},
    #                {"key": "text_start", "values": [f"{text_start}"]},
    #                {"key": "img_size", "values": [f"img#{image_width}px #{image_height}px"]},
    #                {"key": "img_url", "values": [f"{url}"]},
    #                {"key": "text_end", "values": [f"{text_end}"]},
    #                ]
    # })

    # keyboard = MessageKeyboard.model_validate({
    #     "id": "102083290_1707209565"
    # })

    keyboard = MessageKeyboard.model_validate({
        "id": f"{keyboard_template_id}"
    })
    # keyboard = MessageKeyboard.model_validate({
    #     "content": {
    #         "rows": [{"buttons": [
    #             {
    #                 "id": "1",
    #                 "render_data": {
    #                     "label": f"{button_show}",
    #                     "visited_label": f"{button_show}",
    #                     "style": 0
    #                 },
    #                 "action": {
    #                     "type": 2,
    #                     "permission": {
    #                         "type": 2,
    #                     },
    #                     "unsupport_tips": "客户端不支持",
    #                     "data": f"{button_cmd}",
    #                 }
    #             }
    #
    #         ]},
    #             {"buttons": [
    #                 {
    #                     "id": "1",
    #                     "render_data": {
    #                         "label": f"{button_show2}",
    #                         "visited_label": f"{button_show2}",
    #                         "style": 0
    #                     },
    #                     "action": {
    #                         "type": 2,
    #                         "permission": {
    #                             "type": 2,
    #                         },
    #                         "unsupport_tips": "客户端不支持",
    #                         "data": f"{button_cmd2}",
    #                     }
    #                 },
    #                 {
    #                     "id": "1",
    #                     "render_data": {
    #                         "label": f"{button_show3}",
    #                         "visited_label": f"{button_show3}",
    #                         "style": 0
    #                     },
    #                     "action": {
    #                         "type": 2,
    #                         "permission": {
    #                             "type": 2,
    #                         },
    #                         "unsupport_tips": "客户端不支持",
    #                         "data": f"{button_cmd3}",
    #                     }
    #                 },
    #                 {
    #                     "id": "1",
    #                     "render_data": {
    #                         "label": f"{button_show4}",
    #                         "visited_label": f"{button_show4}",
    #                         "style": 0
    #                     },
    #                     "action": {
    #                         "type": 0,
    #                         "permission": {
    #                             "type": 2,
    #                         },
    #                         "unsupport_tips": "客户端不支持",
    #                         "data": f"{button_cmd4}",
    #                     }
    #                 }
    #
    #             ]}
    #         ]
    #     }
    # })

    qq_msg = QQ_Msg([QQ_MsgSeg.markdown(md), QQ_MsgSeg.keyboard(keyboard)])
    return qq_msg


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
        if user_id:
            title = f"<@{user_id}> 当前平台无法登录"
        else:
            title = f"当前平台无法登录"

    return await text_msg_md(title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def push_md(user_id) -> QQ_Msg:
    """无法使用login时转kook登录的md卡片提示"""
    keyboard_template_type = "kook_url"
    data1 = "QQ平台不支持/push的主动推送战绩功能，该功能可在其他平台小鱿鱿bot如kook平台使用"
    data2 = f"Kook服务器id：{plugin_config.splatoon3_kk_guild_id}"
    data3 = ""
    if user_id:
        title = f"<@{user_id}> 当前平台无法使用此功能"
    else:
        title = f"当前平台无法使用此功能"

    return await text_msg_md(title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def more_nso_help_md(user_id) -> QQ_Msg:
    """nso帮助的二级md按钮菜单"""
    keyboard_template_type = "more_nso_help"
    data1 = f"nso相关查询功能太多，下面列举的也不是全部功能，只是提供常用功能的一个快捷方式"
    data2 = f"全部完整的功能和详细用法说明可以点击下面  全部nso指令"
    data3 = f""
    if user_id:
        title = f"<@{user_id}>"
    else:
        title = f""

    return await text_msg_md(title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def report_md(user_id, title, msg) -> QQ_Msg:
    """日报md菜单，将日报文本展示在文本md中，按钮使用nso通用按钮组"""
    keyboard_template_type = "nso_general"
    data1 = f"{msg}"
    data2 = f""
    data3 = f""
    if user_id:
        title = f"<@{user_id}> {title}"

    return await text_msg_md(title=title, data1=data1, data2=data2, data3=data3,
                             keyboard_template_type=keyboard_template_type)


async def text_msg_md(title: str = "", data1: str = "", data2: str = "", data3: str = "",
                      keyboard_template_type="") -> QQ_Msg:
    """
    通用的 文本引用消息md模版
    可提供 titile  title模版前面是引号开头
    引用文本  data1，data2，data3  这三个也支持\n进行换行   至少需要提供一个data1 data2和data3可以不给
    按钮模版类型 若不提供则没有按钮
    """
    # 固定的文本模版id
    template_id = "102083290_1705923685"

    keyboard_template_id = ""
    if keyboard_template_type == "kook_url":
        # kook 服务器的链接 按钮模版
        keyboard_template_id = "102083290_1721647351"
    if keyboard_template_type == "more_nso_help":
        # 更多nso指令 按钮模版
        keyboard_template_id = "102083290_1772274485"
    if keyboard_template_type == "nso_general":
        # 也使用nso通用的 按钮模版
        keyboard_template_id = "102083290_1772274396"

    params = []
    if title:
        params.append({"key": "title", "values": [f"{md_text_replace(title)}"]})
    if data1:
        params.append({"key": "data1", "values": [f"{md_text_replace(data1)}"]})
    if data2:
        params.append({"key": "data2", "values": [f"{md_text_replace(data2)}"]})
    if data3:
        params.append({"key": "data3", "values": [f"{md_text_replace(data3)}"]})

    md = MessageMarkdown.model_validate({
        "custom_template_id": f"{template_id}",
        "params": params
    })

    msg_data_list = [QQ_MsgSeg.markdown(md)]
    # 是否添加按钮
    if keyboard_template_id:
        keyboard = MessageKeyboard.model_validate({
            "id": f"{keyboard_template_id}"
        })
        msg_data_list.append(QQ_MsgSeg.keyboard(keyboard))
    qq_msg = QQ_Msg(msg_data_list)
    return qq_msg


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
    if not content:
        content = "\r"
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


async def get_qq_face_md(user_id: str, url: str) -> QQ_Msg:
    """转发表情用md结构"""
    template_id = "102083290_1705920931"

    image_width, image_height = (500, 500)

    text_start = "图片尺寸以下载为准，此处预览不准"

    params = []
    if user_id:
        params.append({"key": "at_user_id", "values": [f"<@{user_id}>"]})
    params.extend(
        [
            {"key": "text_start", "values": [f"{text_start}"]},
            {"key": "img_size", "values": [f"img#{image_width}px #{image_height}px"]},
            {"key": "img_url", "values": [f"{url}"]},
        ]
    )
    md = QQ_MsgMarkdown.model_validate(
        {"custom_template_id": f"{template_id}", "params": params}
    )

    qq_msg = QQ_Msg([QQ_MsgSeg.markdown(md)])
    return qq_msg


def md_text_replace(text: str):
    return text.replace("\\n", "\r").replace("\n", "\r").replace("\\r", "\r")
