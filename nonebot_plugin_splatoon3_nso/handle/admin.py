import asyncio
import threading
import time

from .cron import create_get_user_friends_tasks, get_x_player, create_set_report_tasks, sync_stat_ink, send_report_task, \
    create_refresh_token_tasks, update_s3si_ts, clean_s3s_cache, clean_global_user_info_dict, get_event_top, \
    show_dict_status
from .cron.else_cron import get_dict_status
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

    match plain_text:

        case "get_push":
            users = dict_get_all_global_users(False)
            msg = ""
            for u in users:
                if not u.push:
                    continue
                msg_id = get_msg_id(u.platform, u.user_id)
                msg += f"db_id:{u.db_id:>3},{msg_id}, n:{u.user_name:>7}, cnt:{u.push_cnt:>3}, g:{u.game_name}\n"
            msg = f"```\n{msg}```" if msg else "no data"
            await bot_send(bot, event, message=msg)

        case "close_push":
            users = dict_get_all_global_users(False)
            msg = ""
            push_cnt = 0
            for u in users:
                if not u.push:
                    continue
                msg = "push推送被管理员强制关闭，大概率是需要重启bot，请稍等几分钟完成重启后，重新对bot发送/push 命令\n"
                # 获取统计数据
                st_msg, _ = close_push(u.platform, u.user_id)
                msg += st_msg
                await notify_to_private(u.platform, u.user_id, msg)
                push_cnt += 1
                time.sleep(0.5)

            await bot_send(bot, event, message=f"已关闭全部{push_cnt}个push")

        case "parse_x_rank":
            await bot_send(bot, event, message="即将开始parse_x_rank")
            await get_x_player()

        case "get_event_top":
            await bot_send(bot, event, message="即将开始get_event_top")
            await get_event_top()

        case "clean_cache":
            model_clean_db_cache()
            await bot_send(bot, event, message="数据库缓存已清空")

        case "set_report":
            await bot_send(bot, event, message="即将开始整理日报")
            await create_set_report_tasks()

        case "send_report":
            await bot_send(bot, event, message="即将开始send_report")
            await send_report_task()

        case "get_user_friends":
            await create_get_user_friends_tasks()

        case "refresh_token":
            await bot_send(bot, event, message="即将开始refresh_token")
            await create_refresh_token_tasks()

        case "update_s3si_ts":
            await bot_send(bot, event, message="即将开始update_s3si_ts")
            await update_s3si_ts()

        case "sync_stat_ink":
            await bot_send(bot, event, message="即将开始sync_stat_ink")
            threading.Thread(target=asyncio.run, args=(sync_stat_ink(),)).start()

        case "clean_s3s_cache":
            await bot_send(bot, event, message="即将开始clean_s3s_cache")
            await clean_s3s_cache()

        case "clean_global_user_info_dict":
            await bot_send(bot, event, message="即将开始clean_global_user_info_dict")
            await clean_global_user_info_dict()

        case "status":
            msg = get_dict_status()
            await bot_send(bot, event, message=msg)
            await show_dict_status()
