import asyncio
import threading
import time

from .cron import create_get_user_friends_tasks, get_x_player, create_set_report_tasks, sync_stat_ink, send_report_task, \
    create_refresh_token_tasks, update_s3si_ts, clean_s3s_cache, clean_global_user_info_dict, get_event_top, \
    show_dict_status
from .cron.else_cron import get_dict_status
from .push import close_push
from .send_msg import bot_send, notify_to_private
from ..data.data_source import dict_get_all_global_users, model_clean_db_cache, model_get_or_set_user, \
    dict_get_or_set_user_info
from ..utils import get_msg_id
from ..utils.bot import *
from nonebot import logger

global_admin_session_token: str = ""

matcher_admin = on_command("admin", block=True, permission=SUPERUSER)


@matcher_admin.handle()
async def admin_cmd(bot: Bot, event: Event, args: Message = CommandArg()):
    plain_text = args.extract_plain_text().strip()
    global global_admin_session_token
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
                user_bot, user_event, st_msg, _ = close_push(u.platform, u.user_id)
                msg += st_msg
                if user_bot and user_event:
                    try:
                        await bot_send(user_bot, user_event, message=msg)
                    except Exception as e:
                        msg_id = get_msg_id(u.platform, u.user_id)
                        logger.warning(
                            f'msg_id:{msg_id} private notice error: {e}')
                push_cnt += 1
                time.sleep(0.5)

            await bot_send(bot, event, message=f"已关闭全部{push_cnt}个push")

        case "get_x_player":
            await bot_send(bot, event, message="即将开始get_x_player")
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
            await bot_send(bot, event, message="即将开始get_user_friends")
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

        case "clean_user_info_dict":
            await bot_send(bot, event, message="即将开始clean_global_user_info_dict")
            await clean_global_user_info_dict()

        case "status":
            msg = get_dict_status()
            await bot_send(bot, event, message=msg)
            await show_dict_status()

        case "restore_token":
            """还原自己token"""
            if not global_admin_session_token:
                await bot_send(bot, event, message=f"未更改token，无需还原")
            else:
                platform = bot.adapter.get_name()
                my_user_id = event.get_user_id()
                dict_get_or_set_user_info(platform, my_user_id, session_token=global_admin_session_token,
                                          access_token="",
                                          g_token="", bullet_token="")
                await bot_send(bot, event, message=f"token已恢复")

        case "help":
            """指令目录"""
            msg = "所有命令都需要加上/admin 前缀\n" \
                  "get_push 获取当前push统计\n" \
                  "close_push 关闭当前全部push\n" \
                  "get_x_player 获取x赛top\n" \
                  "get_event_top 获取活动top\n" \
                  "clean_cache 清理数据库缓存\n" \
                  "set_report 写日报\n" \
                  "send_report 发送日报\n" \
                  "get_user_friends 获取全部用户好友列表\n" \
                  "refresh_token 刷新全部缓存用户token\n" \
                  "update_s3si_ts 更新s3sti脚本\n" \
                  "sync_stat_ink 开始全部用户同步stat\n" \
                  "clean_s3s_cache 清空s3s缓存文件夹\n" \
                  "clean_user_info_dict 清理用户数据缓存字典以及client\n" \
                  "status 当前缓存用户状态以及ss截图调用情况\n" \
                  "kook_leave {guild_id} kook离开服务器\n" \
                  "copy_token {user_id} 复制同平台某用户token，便于调试\n" \
                  "restore_token 还原自身本来token\n"
            await bot_send(bot, event, message=msg)

    if plain_text.startswith("kook_leave"):
        """kook bot离开某服务器
        kook_leave {guild_id}
        """
        args = plain_text.split(" ")
        if len(args) == 2:
            guild_id = args[1]
            await bot.guild_leave(guild_id=guild_id)
            await bot_send(bot, event, message=f"已退出服务器{guild_id}")
        else:
            await bot_send(bot, event, message=f"无效命令， lens:{len(args)}")

    if plain_text.startswith("copy_token"):
        """复制同平台其他用户token到自己账号，方便测试"""
        args = plain_text.split(" ")
        if len(args) == 2:
            platform = bot.adapter.get_name()
            user_id = args[1]
            my_user_id = event.get_user_id()
            user = model_get_or_set_user(platform, user_id)
            my = model_get_or_set_user(platform, my_user_id)
            # 备份自己cookies
            if not global_admin_session_token:
                global_admin_session_token = my.session_token
            if not user:
                await bot_send(bot, event, message=f"{platform}平台用户{user_id} 数据不存在")
                return False
            # 设置别人的值
            dict_get_or_set_user_info(platform, my_user_id, session_token=user.session_token, access_token="",
                                      g_token="", bullet_token="")
            await bot_send(bot, event,
                           message=f"已复制账号 db_id:{user.id},msg_id:{get_msg_id(user.platform, user.user_id)},\ngame_name:{user.game_name}\n还原:/admin restore_token")
        else:
            await bot_send(bot, event, message=f"无效命令， lens:{len(args)}")
