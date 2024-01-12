from .utils import bot_send, _check_session_handler
from ..data.data_source import model_get_or_set_user
from ..utils.bot import *


@on_command("show_db_info", aliases={'sdi'}, priority=10, block=True).handle(
    parameterless=[Depends(_check_session_handler)])
async def show_db_info(bot: Bot, event: Event):
    if 'group' in event.get_event_name():
        await bot_send(bot, event, '请私聊机器人')
        return
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg = get_user_db_info(platform, user_id)

    await bot_send(bot, event, msg)


def get_user_db_info(platform, user_id):
    """获取用户数据库数据"""
    user = model_get_or_set_user(platform, user_id)
    msg = f"""
```
user_name: {user.username}
gtoken: {user.gtoken}
bullettoken: {user.bullettoken}
session_token: {user.session_token}
push: {user.push}
push_cnt: {user.push_cnt}
api_key: {user.api_key}
user_info: {user.user_info}
```
/clear\_db\_info  clear your data
"""
    return msg
