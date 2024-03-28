from nonebot.adapters.qq.models import MessageKeyboard, MessageMarkdown

from ..config import plugin_config
from ..utils.bot import *


def last_md(user_id, image_size: tuple, url: str) -> QQ_Msg:
    """为/last查询拼装md结构"""
    template_id = "102083290_1705920931"
    image_width, image_height = image_size
    text_start = "发送/nso帮助查看详细用法"
    text_end = "自己手动/last也算是一种push推送吧"
    button_show = "/last"
    button_cmd = "/last"

    button_show2 = "/last b"
    button_cmd2 = "/last b"

    button_show3 = "/last c"
    button_cmd3 = "/last c"

    # 如果kv值为空，那只能不传，空值似乎最多只允许一个

    md = MessageMarkdown.model_validate({
        "custom_template_id": f"{template_id}",
        "params": [{"key": "at_user_id", "values": [f"<@{user_id}>"]},
                   {"key": "text_start", "values": [f"{text_start}"]},
                   {"key": "img_size", "values": [f"img#{image_width}px #{image_height}px"]},
                   {"key": "img_url", "values": [f"{url}"]},
                   ]
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

    keyboard = MessageKeyboard.model_validate({
        "id": "102083290_1707209565"
    })
    qq_msg = QQ_Msg([QQ_MsgSeg.markdown(md), QQ_MsgSeg.keyboard(keyboard)])
    return qq_msg


def login_md(user_id, check_session=False) -> QQ_Msg:
    template_id = "102083290_1705923685"
    data1 = ""
    if check_session:
        data1 += "nso未登录，无法使用相关查询，"
    data1 += "QQ平台当前无法完成登录流程，请至其他平台完成登录后使用 /getlc 命令获取绑定码"
    data2 = f"Kook服务器id：{plugin_config.splatoon3_kk_guild_id}"
    button_show = "kook服务器"
    kook_jump_link = "https://www.kookapp.cn/app/invite/mkjIOn"

    md = MessageMarkdown.model_validate({
        "custom_template_id": f"{template_id}",
        "params": [{"key": "title", "values": [f"<@{user_id}>"]},
                   {"key": "data1", "values": [f"{data1}"]},
                   {"key": "data2", "values": [f"{data2}"]},
                   ]
    })

    keyboard = MessageKeyboard.model_validate({
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
                        "type": 0,
                        "permission": {
                            "type": 2,
                        },
                        "unsupport_tips": "客户端不支持",
                        "data": f"{kook_jump_link}",
                    }
                }

            ]},
            ]
        }
    })
    qq_msg = QQ_Msg([QQ_MsgSeg.markdown(md), QQ_MsgSeg.keyboard(keyboard)])
    return qq_msg
