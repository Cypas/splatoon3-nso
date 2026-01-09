import asyncio
import datetime
import gc
import time

from .utils import cron_logger, user_remove_duplicates
from datetime import datetime as dt, timedelta

from ..report import get_report
from ..send_msg import notify_to_private, cron_notify_to_channel
from ...data.db_sqlite import Report
from ...handle.utils import get_battle_time_or_coop_time, get_game_sp_id
from ...data.data_source import model_add_report, model_get_all_user, dict_get_or_set_user_info, model_get_or_set_user, \
    model_get_today_report, dict_clear_user_info_dict, model_get_temp_image_path, global_user_info_dict, \
    dict_get_all_global_users
from ...s3s.splatoon import Splatoon
from ...utils import get_msg_id, convert_td, ReqClient
from ...utils.bot import *


async def create_set_report_tasks(is_corn_job=True):
    """8点时请求并提前写好日报数据"""
    cron_msg = f'create_set_report_tasks phase1_tasks start'.center(60, "=")
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("set_report", "start")

    t = dt.utcnow()
    db_users = model_get_all_user()
    db_users = user_remove_duplicates(db_users)

    list_user: list[tuple] = [(user.platform, user.user_id) for user in db_users]

    # 阶段计数器
    counters = {"refresh_tokens_fail_count": 0,
                "data_missing_count": 0,
                "no_report_count": 0,
                "set_report_count": 0,
                }

    # 阶段1：认证刷新池（并发限制2）
    phase1_semaphore = asyncio.Semaphore(4)
    # 阶段2：报告生成池（并发限制4）
    phase2_semaphore = asyncio.Semaphore(4)

    # ================== 阶段1：认证刷新 ==================
    async def process_phase1(p_and_id):
        async with phase1_semaphore:
            platform, user_id = p_and_id
            msg_id = get_msg_id(platform, user_id)

            # 检查全局缓存
            global_user_info = global_user_info_dict.get(msg_id)
            if global_user_info:
                return Splatoon(None, None, global_user_info)  # 直接返回已存在的对象

            # 新建cron任务对象
            u = dict_get_or_set_user_info(platform, user_id, _type="cron")
            if not u or not u.session_token:
                return None

            try:
                splatoon = Splatoon(None, None, u, _type="cron")
                # 测试访问并刷新
                success = await splatoon.test_page()
                # success = await splatoon.refresh_gtoken_and_bullettoken()
                return splatoon  # 返回初始化完成的对象
            except ValueError as e:
                if any(key in str(e) for key in ['invalid_grant', 'Membership required', 'has be banned']):
                    cron_logger.info(f"跳过无效用户: {msg_id}，reason:{e}")
                    return None

    # 阶段1
    phase1_tasks = [process_phase1(p_and_id) for p_and_id in list_user]
    phase1_splatoons = await asyncio.gather(*phase1_tasks)

    # ================== 等待 UTC 0 点后再执行阶段2 ==================
    def get_seconds_until_utc_midnight() -> int:
        """计算当前 UTC 时间距离下一个 UTC 0 点的秒数（纯 datetime 计算，无时区依赖）"""
        if not is_corn_job:
            # 手动触发时，直接继续执行
            return 0
        now_utc = dt.utcnow()  # now_utc 是 datetime.datetime 类型（UTC 时间，无时区属性）
        # 构造当天 UTC 0 点（纯 datetime 对象，无时区）
        next_midnight = dt(
            year=now_utc.year,
            month=now_utc.month,
            day=now_utc.day,
            hour=0,
            minute=0,
            second=0
        ) + datetime.timedelta(days=1)  # 关键：直接+1天，得到次日0点
        # 计算当前时间到次日0点的秒数
        delta = next_midnight - now_utc
        return int(delta.total_seconds())

    # 计算需要等待的秒数
    wait_seconds = get_seconds_until_utc_midnight()
    if wait_seconds > 0:
        cron_logger.info(f"阶段2需等待 UTC 0 点，当前等待秒数：{wait_seconds}s")
        # 异步等待（不阻塞事件循环）
        await asyncio.sleep(wait_seconds)
    else:
        cron_logger.info("当前已过 UTC 0 点，直接执行阶段2")

    # ================== 阶段2：报告生成 ==================
    cron_logger.info("create_set_report_tasks phase2_tasks start".center(60, "="))
    valid_splatoons = [s for s in phase1_splatoons if s is not None]

    async def process_phase2(splatoon: Splatoon):
        async with phase2_semaphore:
            if splatoon is None:
                return
            result = await set_user_report_task(
                (splatoon.platform, splatoon.user_id),
                splatoon
            )
            await splatoon.close()
            del splatoon  # 解除强引用
            gc.collect()  # 即时回收

            if result:
                if result == "refresh_tokens fail":
                    counters["refresh_tokens_fail_count"] += 1
                if result == "data missing":
                    counters["data_missing_count"] += 1
                if result == "no report":
                    counters["no_report_count"] += 1
                if result == "success":
                    counters["set_report_count"] += 1

    # 阶段2
    phase2_tasks = [process_phase2(s) for s in valid_splatoons]
    await asyncio.gather(*phase2_tasks)

    # 结果报告
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = (f"create_set_report_tasks end: {str_time}\n"
                f"全部用户: {len(list_user)}\n"
                f"有效用户: {len(valid_splatoons)}\n"
                f"刷新成功: {len(valid_splatoons) - counters['refresh_tokens_fail_count']}\n"
                f"无日报: {counters['no_report_count']}\n"
                f"成功写日报: {counters['set_report_count']}\n")
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("set_report", "end",
                                 f"耗时:{str_time}\n"
                                 f"全部用户: {len(list_user)}\n"
                                 f"有效用户:{len(valid_splatoons)}\n"
                                 f"刷新成功: {len(valid_splatoons) - counters['refresh_tokens_fail_count']}\n"
                                 f"无日报: {counters['no_report_count']}\n"
                                 f"成功写日报:{counters['set_report_count']}\n")
    # 清理临时任务对象
    await ReqClient.close_all(_type="cron")

    # 发信
    await send_report_task()


async def set_user_report_task(p_and_id, splatoon: Splatoon):
    """任务: 写用户最后游玩数据及日报数据（精确处理版，修复内存泄漏）"""
    platform, user_id = p_and_id
    msg_id = get_msg_id(platform, user_id)

    cron_logger.info(f'start set_report: {msg_id}, {splatoon.user_name}')
    # 再次校验是否有访问权限
    success = False
    try:
        success = await splatoon.test_page()
    except ValueError as e:
        # 预期错误，token更新失败
        cron_logger.debug(f'set_report error: {msg_id}, {splatoon.user_name},reason：{e}')
        # 失败时立即清理
        await splatoon.close()
        del splatoon
        gc.collect()
        return "refresh_tokens fail"

    if not success:
        # 无效token
        cron_logger.error(f'set_report error: {msg_id}, {splatoon.user_name},refresh_tokens fail')
        # 失败时立即清理
        await splatoon.close()
        del splatoon
        gc.collect()
        return "refresh_tokens fail"

    try:
        # ================== 并发执行所有请求（修复闭包引用） ==================
        # 方案：提前绑定方法，避免lambda闭包持有splatoon引用
        tasks = [
            fetch_with_retry(
                splatoon.get_history_summary,  # 直接传方法，而非lambda闭包
                splatoon.get_history_summary,
                multiple=True  # 传递参数，避免闭包
            ),
            fetch_with_retry(
                splatoon.get_recent_battles,
                splatoon.get_recent_battles,
                multiple=True
            ),
            fetch_with_retry(
                splatoon.get_coops,
                splatoon.get_coops,
                multiple=True
            ),
            fetch_with_retry(
                splatoon.get_total_query,
                splatoon.get_total_query,
                multiple=True
            )
        ]

        # 同时执行所有任务
        res_summary, res_battle, res_coop, all_data = await asyncio.gather(*tasks)

        # ================== 数据校验 ==================
        if not all([res_summary, res_battle, res_coop, all_data]):
            missing = []
            if not res_summary: missing.append("summary")
            if not res_battle: missing.append("battle")
            if not res_coop: missing.append("coop")
            if not all_data: missing.append("all_data")
            cron_logger.error(f"数据缺失: {msg_id} 缺失字段: {missing}")
            return "data missing"

        # ================== 对战数据处理 ==================
        try:
            b_info = \
                res_battle['data']['latestBattleHistories']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]
            battle_t = get_battle_time_or_coop_time(b_info['id'])
            game_sp_id = get_game_sp_id(b_info['player']['id'])
        except (KeyError, IndexError) as e:
            cron_logger.error(f"对战数据解析失败: {msg_id} 错误类型: {type(e).__name__}")
            return "data missing"

        # ================== 打工数据处理 ==================
        try:
            coop_node = res_coop['data']['coopResult']['historyGroups']['nodes'][0]
            coop_detail = coop_node['historyDetails']['nodes'][0]
            coop_t = get_battle_time_or_coop_time(coop_detail['id'])
        except (KeyError, IndexError) as e:
            cron_logger.error(f"打工数据解析失败: {msg_id} 错误类型: {type(e).__name__}")
            return "data missing"

        # ================== 时间计算 ==================
        last_play_time = max(dt.strptime(battle_t, '%Y%m%dT%H%M%S'), dt.strptime(coop_t, '%Y%m%dT%H%M%S'))

        # ================== 剩余业务逻辑 ==================
        # 上次游玩时间位于一天内
        if last_play_time.date() >= (dt.utcnow() - timedelta(days=1)).date():
            await set_user_report(
                splatoon.user_db_info.db_id, res_summary, res_coop,
                last_play_time, splatoon, game_sp_id, all_data
            )
            cron_logger.info(f'set_user_report_task success: {msg_id}')
            # 成功
            return "success"

        # 无日报
        return "no report"
    except Exception as ex:
        cron_logger.error(f'set_user_report_task error: {msg_id} error:{str(ex)}', exc_info=True)
        # 异常时清理

        return False
    finally:
        if 'splatoon' in locals() and splatoon is not None:
            await splatoon.close()
            del splatoon
            gc.collect()


async def fetch_with_retry(coro_func, retry_func, **kwargs):
    """带一次重试的通用请求函数（修复闭包引用）"""
    try:
        result = await coro_func(**kwargs)  # 直接调用方法并传参
        if result: return result
    except Exception as e:
        cron_logger.debug(f"首次请求失败: {str(e)}")

    try:
        return await retry_func(**kwargs)
    except Exception as e:
        cron_logger.warning(f"重试请求失败: {str(e)}")
        return None


async def set_user_report(user_db_id, res_summary, res_coop, last_play_time, splatoon, player_code, all_data):
    """写用户日报数据"""
    history = res_summary['data']['playHistory']
    player = res_summary['data']['currentPlayer']
    nickname = player['name']

    total_cnt = all_data['data']['playHistory']['battleNumTotal']
    win_cnt = history['winCountTotal']
    lose_cnt = total_cnt - win_cnt
    win_rate = round(win_cnt / total_cnt * 100, 2)

    _l = history['leagueMatchPlayHistory']
    _ln = _l['attend'] - _l['gold'] - _l['silver'] - _l['bronze']
    _o = history['bankaraMatchOpenPlayHistory']
    _on = _o['attend'] - _o['gold'] - _o['silver'] - _o['bronze']

    ar = round((history.get('xMatchMaxAr') or {}).get('power') or 0, 2) or None
    lf = round((history.get('xMatchMaxLf') or {}).get('power') or 0, 2) or None
    gl = round((history.get('xMatchMaxGl') or {}).get('power') or 0, 2) or None
    cl = round((history.get('xMatchMaxCl') or {}).get('power') or 0, 2) or None
    max_power = max(ar or 0, lf or 0, gl or 0, cl or 0) or None

    coop = res_coop['data']['coopResult']
    card = coop['pointCard']
    p = coop['scale']

    _report = {
        'user_id': user_db_id,
        'user_id_sp': player_code,
        'nickname': nickname,
        'name_id': player['nameId'],
        'byname': player['byname'],
        'rank': history['rank'],
        'udemae': history['udemae'],
        'udemae_max': history['udemaeMax'],
        'total_cnt': total_cnt,
        'win_cnt': win_cnt,
        'lose_cnt': lose_cnt,
        'win_rate': win_rate,
        'paint': history['paintPointTotal'],
        'badges': len(history['badges']),
        'event_gold': _l['gold'],
        'event_silver': _l['silver'],
        'event_bronze': _l['bronze'],
        'event_none': _ln,
        'open_gold': _o['gold'],
        'open_silver': _o['silver'],
        'open_bronze': _o['bronze'],
        'open_none': _on,
        'max_power': max_power,
        'x_ar': ar,
        'x_lf': lf,
        'x_gl': gl,
        'x_cl': cl,
        'coop_cnt': card['playCount'],
        'coop_gold_egg': card['goldenDeliverCount'],
        'coop_egg': card['deliverCount'],
        'coop_boss_cnt': card['defeatBossCount'],
        'coop_rescue': card['rescueCount'],
        'coop_point': card['totalPoint'],
        'coop_gold': p['bronze'],
        'coop_silver': p['silver'],
        'coop_bronze': p['gold'],
        'last_play_time': last_play_time,
    }
    if player_code:
        new_report = Report(**_report)
        model_add_report(new_report)


async def send_report_task():
    """9点时进行发信"""
    report_logger = logger.bind(report=True)
    cron_msg = f'create_send_report_tasks start'.center(60, "=")
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("send_report", "start")
    t = dt.utcnow()

    # 阶段计数器
    counters = {"new_report_count": 0,
                "can_send_report_count": 0,
                "error_kook_send_limit": 0,
                "error_user_ban_bot": 0,
                }

    users = model_get_all_user()
    for user in users:
        msg_id = get_msg_id(user.platform, user.user_id)
        # 根据sp_id查询今天是否生成新日报
        have_report = model_get_today_report(user.game_sp_id)
        if not have_report:
            continue
        counters["new_report_count"] += 1
        # 排除qq平台发信 和 日报通知未打开的用户
        if user.platform == "QQ" or not user.report_notify:
            continue
        counters["can_send_report_count"] += 1
        # 每次循环强制睡眠1s，使一分钟内不超过120次发信阈值
        await asyncio.sleep(1)
        try:
            msg = get_report(user.platform, user.user_id, _type="cron")
            if msg:
                # 写日志
                log_msg = msg.replace('\n', '')
                report_logger.info(f"get db_id:{user.id},msg_id:{msg_id} report：{log_msg}")
                # # 通知到频道
                # await report_notify_to_channel(user.platform, user.user_id, msg, _type='job')
                # 通知到私信
                msg += "\n/report_notify close 关闭每日日报推送"
                await notify_to_private(user.platform, user.user_id, msg)
        except Kook_ActionFailed as e:
            if e.status_code == 40000:
                if e.message.startswith("无法发起私信"):
                    counters["error_kook_send_limit"] += 1
                    time.sleep(10)
                elif e.message.startswith("你已被对方屏蔽"):
                    model_get_or_set_user(user.platform, user.user_id, stat_notify=0, report_notify=0)
                    cron_logger.warning(
                        f'create_send_report_tasks error:{msg_id},error:用户已屏蔽发信bot，已关闭其通知权限')
                    counters["error_user_ban_bot"] += 1
            continue
        except Exception as e:
            cron_logger.warning(f'create_send_report_tasks error:{msg_id},error:{e}')
            continue

    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = (f"create_send_report_tasks end: {str_time}\n"
                f"new_report_count: {counters['new_report_count']},can_send_report_count: {counters['can_send_report_count']}\n"
                f"error_kook_send_limit: {counters['error_kook_send_limit']},error_user_ban_bot: {counters['error_user_ban_bot']}")
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("send_report", "end",
                                 f"耗时:{str_time}\n"
                                 f"全部日报: {counters['new_report_count']},待发送日报:{counters['can_send_report_count']}\n"
                                 f"发送限速: {counters['error_kook_send_limit']},bot被屏蔽:{counters['error_user_ban_bot']}\n"
                                 )
