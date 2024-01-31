import json

from nonebot.adapters.qq.message import Keyboard
from nonebot.adapters.qq.models import MessageKeyboard, InlineKeyboard, InlineKeyboardRow, Button, RenderData, \
    MessageMarkdown

from ..utils.bot import *


def last_md(user_id, image_size: tuple, url: str) -> QQ_Msg:
    """为/last查询拼装md结构"""
    template_id = "101993071_1658748972"
    image_width, image_height = image_size
    text_start = ""
    text_end = ""
    button_show = "/last"
    button_cmd = "/last"

    md = MessageMarkdown.parse_obj({
        "custom_template_id": f"{template_id}",
        "params": [{"key": "at_user_id", "values": [f"<@{user_id}>"]},
                   {"key": "text_start", "values": [f"{text_start}"]},
                   {"key": "img_size", "values": [f"img#{image_width}px #{image_height}px"]},
                   {"key": "img_url", "values": [f"{url}"]},
                   {"key": "text_end", "values": [f"{text_end}"]},
                   ]
    })

    keyboard = MessageKeyboard.parse_obj({
        "content": {
            "rows": [{"buttons": [
                {
                    "id": "1",
                    "render_data": {
                        "label": f"{button_show}",
                        "visited_label": f"{button_show}",
                        "style": 0
                    },
                    "action": {
                        "type": 2,
                        "permission": {
                            "type": 2,
                        },
                        "unsupport_tips": "客户端不支持",
                        "data": f"{button_cmd}",
                    }
                }

            ]}]
        }
    })

    # button1 = Button(id="", render_data=RenderData(label=f"{button_show}", visited_label=f"{button_show}", style=0),
    #                  )
    # keyboard = QQ_MsgSeg.keyboard(
    #     MessageKeyboard(id="", content=InlineKeyboard(rows=[InlineKeyboardRow(buttons=[button1])])))

    qq_msg = QQ_Msg([QQ_MsgSeg.markdown(md), QQ_MsgSeg.keyboard(keyboard)])
    return qq_msg
