import re

from nonebot.adapters.qq.models import MessageKeyboard, MessageMarkdown
from nonebot.adapters.telegram.model import InlineKeyboardMarkup

from ..config import plugin_config
from ..data.utils import plugin_data, get_or_set_plugin_data
from ..utils.bot import *


async def last_md(user_id, image_size: tuple, url: str) -> QQ_Msg:
    """为/last查询拼装md结构"""
    template_id = "102083290_1705920931"
    keyboard_template_id = "102083290_1767589971"
    image_width, image_height = image_size
    text_start = "发送/nso帮助查看详细用法"
    # text_end作为公告消息
    text_end = await get_or_set_plugin_data("splatoon3_bot_notice")
    button_show = "查对战或打工"
    button_cmd = "/last"

    button_show2 = "查对战"
    button_cmd2 = "/last b"

    button_show3 = "查打工"
    button_cmd3 = "/last c"

    button_show4 = "bot官方群"
    button_cmd4 = "http://qm.qq.com/cgi-bin/qm/qr?_wv=1027&k=zGefDQ4GQYFPAB-hFkeFLlyQ8qbG5S2w&authKey=j0b9yXmtSzYry6qQQ%2FFXxw7U%2Fp6kXyET0xj%2BRHWxeRa20zvJeN8W91noNrJDmDyO&noverify=0&group_code=827977720"

    # 如果kv值为空，那只能不传，空值似乎最多只允许一个
    params = []
    if user_id:
        params.append({"key": "at_user_id", "values": [f"<@{user_id}>"]})
    params.extend([{"key": "text_start", "values": [f"{text_start}"]},
                   {"key": "img_size", "values": [f"img#{image_width}px #{image_height}px"]},
                   {"key": "img_url", "values": [f"{url}"]}])
    if text_end:
        text_end = text_end.replace("\\n", "\r").replace("\\r", "\r")
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


def login_md(user_id, check_session=False) -> QQ_Msg:
    """无法使用login时转kook登录的md卡片提示"""
    template_id = "102083290_1705923685"
    keyboard_template_id = "102083290_1721647351"
    data1 = ""
    if check_session:
        data1 += "nso未登录，无法使用相关查询，"
    data1 += "QQ平台当前无法完成登录流程，请至其他平台完成登录后使用 /getlc 命令获取绑定码"
    data2 = f"Kook服务器id：{plugin_config.splatoon3_kk_guild_id}"
    button_show = "kook服务器"
    kook_jump_link = "https://www.kookapp.cn/app/invite/mkjIOn"

    params = []
    if user_id:
        params.append({"key": "title", "values": [f"<@{user_id}>"]})
    else:
        params.append({"key": "title", "values": [f"当前平台无法登录"]})
    params.extend([{"key": "data1", "values": [f"{data1}"]},
                   {"key": "data2", "values": [f"{data2}"]},
                   ])

    md = MessageMarkdown.model_validate({
        "custom_template_id": f"{template_id}",
        "params": params
    })

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
    #                     "type": 0,
    #                     "permission": {
    #                         "type": 2,
    #                     },
    #                     "unsupport_tips": "客户端不支持",
    #                     "data": f"{kook_jump_link}",
    #                 }
    #             }
    #
    #         ]},
    #         ]
    #     }
    # })
    qq_msg = QQ_Msg([QQ_MsgSeg.markdown(md), QQ_MsgSeg.keyboard(keyboard)])
    return qq_msg


def c2c_login_md(login_url) -> QQ_Msg:
    """c2c login卡片"""
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


def url_md(title, content, url_title, url) -> QQ_Msg:
    """仅发一个url的按钮卡片"""
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
