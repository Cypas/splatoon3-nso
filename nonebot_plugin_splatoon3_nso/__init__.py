from typing import Union, Tuple

import nonebot
from nonebot.params import RegexGroup
from nonebot.plugin import PluginMetadata
from nonebot import on_regex, Bot, params, require
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State

# onebot11 协议
from nonebot.adapters.onebot.v11 import Bot as V11_Bot
from nonebot.adapters.onebot.v11 import MessageEvent as V11_ME
from nonebot.adapters.onebot.v11 import Message as V11_Msg
from nonebot.adapters.onebot.v11 import MessageSegment as V11_MsgSeg
from nonebot.adapters.onebot.v11 import PrivateMessageEvent as V11_PME
from nonebot.adapters.onebot.v11 import GroupMessageEvent as V11_GME

# onebot12 协议
from nonebot.adapters.onebot.v12 import Bot as V12_Bot
from nonebot.adapters.onebot.v12 import MessageEvent as V12_ME
from nonebot.adapters.onebot.v12 import Message as V12_Msg
from nonebot.adapters.onebot.v12 import MessageSegment as V12_MsgSeg
from nonebot.adapters.onebot.v12 import ChannelMessageEvent as V12_CME
from nonebot.adapters.onebot.v12 import PrivateMessageEvent as V12_PME
from nonebot.adapters.onebot.v12 import GroupMessageEvent as V12_GME

# telegram 协议
from nonebot.adapters.telegram import Bot as Tg_Bot
from nonebot.adapters.telegram.event import MessageEvent as Tg_ME
from nonebot.adapters.telegram import MessageSegment as Tg_MsgSeg
from nonebot.adapters.telegram.event import PrivateMessageEvent as Tg_PME
from nonebot.adapters.telegram.event import GroupMessageEvent as Tg_GME
from nonebot.adapters.telegram.event import ChannelPostEvent as Tg_CME
from nonebot.adapters.telegram.message import File as Tg_File

# kook协议
from nonebot.adapters.kaiheila import Bot as Kook_Bot
from nonebot.adapters.kaiheila.event import MessageEvent as Kook_ME
from nonebot.adapters.kaiheila import MessageSegment as Kook_MsgSeg
from nonebot.adapters.kaiheila.event import PrivateMessageEvent as Kook_PME
from nonebot.adapters.kaiheila.event import ChannelMessageEvent as Kook_CME

# qq官方协议
from nonebot.adapters.qq import Bot as QQ_Bot
from nonebot.adapters.qq.event import MessageEvent as QQ_ME, GroupAtMessageCreateEvent
from nonebot.adapters.qq import MessageSegment as QQ_MsgSeg
from nonebot.adapters.qq.event import GroupAtMessageCreateEvent as QQ_GME  # 群艾特信息
from nonebot.adapters.qq.event import C2CMessageCreateEvent as QQ_C2CME  # Q私聊信息
from nonebot.adapters.qq.event import DirectMessageCreateEvent as QQ_PME  # 频道私聊信息
from nonebot.adapters.qq.event import AtMessageCreateEvent as QQ_CME  # 频道艾特信息


require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="splatoon3游戏nso查询",
    description="一个基于nonebot2框架的splatoon3游戏nso数据查询插件",
    usage="发送 帮助 或 help 可查看详细指令\n",
    type="application",
    # 发布必填，当前有效类型有：`library`（为其他插件编写提供功能），`application`（向机器人用户提供功能）。
    homepage="https://github.com/Cypas/splatoon3-nso",
    # 发布必填。
    supported_adapters={"~onebot.v11", "~onebot.v12", "~telegram", "~kaiheila", "~qq"},
)

BOT = Union[V11_Bot, V12_Bot, Tg_Bot, Kook_Bot, QQ_Bot]
MESSAGE_EVENT = Union[V11_ME, V12_ME, Tg_ME, Kook_ME, QQ_ME]

