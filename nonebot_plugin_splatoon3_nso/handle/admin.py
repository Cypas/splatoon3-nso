import time

from .cron import create_get_user_friends_tasks, get_x_player, create_set_report_tasks, sync_stat_ink, send_report_task, \
    create_refresh_token_tasks, update_s3si_ts
from .push import close_push
from .send_msg import bot_send, notify_to_private
from ..data.data_source import dict_get_all_global_users, model_clean_db_cache
from ..utils import get_msg_id
from ..utils.bot import *

matcher_admin = on_command("admin", block=True, permission=SUPERUSER)


@matcher_admin.handle()
async def admin_cmd(bot: Bot, event: Event, args: Message = CommandArg()):
    plain_text = args.extract_plain_text().strip()
    logger.info(f'admin: {plain_text}')
    if plain_text == 'get_event_top':
        pass
        # from .scripts.top_player import task_get_league_player
        # from .splat import Splatoon, get_or_set_user
        # user_id = event.get_user_id()
        # user = get_or_set_user(user_id=user_id)
        # splt = Splatoon(user_id, user.session_token)
        # await task_get_league_player(splt)
        # await bot_send(bot, event, message=f'get_event_top end')

    elif plain_text == 'get_push':
        users = dict_get_all_global_users(False)
        msg = ''
        for u in users:
            if not u.push:
                continue
            msg_id = get_msg_id(u.platform, u.user_id)
            msg += f'db_id:{u.db_id},{msg_id:>4}, n:{u.user_name}, cnt:{u.push_cnt:>3}, g:{u.game_name}\n'
        msg = f'```\n{msg}```' if msg else 'no data'
        await bot_send(bot, event, message=msg)

    elif plain_text == 'close_push':
        users = dict_get_all_global_users(False)
        msg = ''
        for u in users:
            if not u.push:
                continue
            msg = 'push推送被管理员强制关闭，大概率是需要重启bot，请稍等几分钟完成重启后，重新对bot发送/push 命令\n'
            # 获取统计数据
            st_msg = close_push(u.platform, u.user_id)
            msg += st_msg
            await notify_to_private(u.platform, u.user_id, msg)
            time.sleep(0.5)

        await bot_send(bot, event, message="已关闭所有push")

    elif plain_text == 'parse_x_rank':
        await bot_send(bot, event, message="即将开始parse_x_rank")
        await get_x_player()

    elif plain_text == 'clean_cache':
        model_clean_db_cache()
        await bot_send(bot, event, message="数据库缓存已清空")

    elif plain_text == 'set_report':
        await bot_send(bot, event, message="即将开始整理日报")
        await create_set_report_tasks()

    elif plain_text == 'send_report':
        await bot_send(bot, event, message="即将开始send_report")
        await send_report_task()

    elif plain_text == 'get_user_friends':
        await create_get_user_friends_tasks()

    elif plain_text == 'refresh_token':
        await bot_send(bot, event, message="即将开始refresh_token")
        await create_refresh_token_tasks()

    elif plain_text == 'update_s3si_ts':
        await bot_send(bot, event, message="即将开始update_s3si_ts")
        update_s3si_ts()

    elif plain_text == 'sync_stat_ink':
        await bot_send(bot, event, message="即将开始sync_stat_ink")
        await sync_stat_ink()
