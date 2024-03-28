import datetime
from datetime import datetime as dt, timedelta

from .send_msg import bot_send
from .utils import _check_session_handler
from ..data.data_source import dict_get_or_set_user_info, model_get_report, model_get_report_all
from ..utils.bot import *


@on_command("report", priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def report(bot: Bot, event: Event, args: Message = CommandArg()):
    """日报统计查询"""
    cmd_list = args.extract_plain_text().strip()
    report_day = ''
    if cmd_list:
        report_day = cmd_list
        try:
            dt.strptime(report_day, '%Y-%m-%d')
        except:
            msg = "日期格式错误，正确格式: /report 2023-07-01 或 /report"
            await bot_send(bot, event, message=msg)
            return
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    msg = get_report(platform, user_id, report_day=report_day)
    if not msg:
        if not report_day:
            msg = f"```\n数据准备中，请明天再查询\n```"
        elif report_day:
            msg = f"```\n没有查询到所指定日期的日报数据```"

    await bot_send(bot, event, message=msg)


def get_report(platform, user_id, report_day=None, _type="normal"):
    """获取昨天或指定日期的早报数据"""
    msg = "\n喷喷早报\n"
    if report_day:
        msg = "\n喷喷小报\n"

    u = dict_get_or_set_user_info(platform, user_id, _type=_type)
    report_list = model_get_report(user_id_sp=u.game_sp_id, create_time=report_day)

    if not report_list or len(report_list) == 1:
        return

    old = report_list[1]

    fst_day = ''
    if report_day:
        fst_day = report_list[-1].create_time.strftime('%Y-%m-%d')
        for r in report_list[::-1]:
            if r.last_play_time.strftime('%Y-%m-%d') < max(report_day, fst_day):
                old = r
                break

    new = report_list[0]
    s_date = (old.create_time + timedelta(hours=8)).strftime('%Y%m%d')
    if report_day:
        s_date = max(report_day.replace('-', ''), s_date)
    e_date = (new.last_play_time + timedelta(hours=8)).strftime('%Y%m%d %H:%M')
    msg += f'统计区间HKT: {s_date[2:]} 08:00 ~ {e_date[2:]}\n\n'

    msg += f'{new.nickname}\n'
    for k in ('nickname', 'name_id', 'byname'):
        if getattr(old, k) != getattr(new, k):
            msg += f'{getattr(old, k)} -> {getattr(new, k)}\n'
    if old.rank != new.rank:
        msg += f'等级: {old.rank} -> {new.rank}\n'
    if old.udemae != new.udemae:
        msg += f'技术: {old.udemae} -> {new.udemae}\n'
    if old.udemae_max != new.udemae_max:
        msg += f'最高技术: {old.udemae_max} -> {new.udemae_max}\n'
    if old.total_cnt != new.total_cnt:
        rate_diff = round(new.win_rate - old.win_rate, 2)
        msg += f'总胜利数: (+{new.win_cnt - old.win_cnt}){new.win_cnt}/(+{new.total_cnt - old.total_cnt}){new.total_cnt} ({rate_diff:+}){new.win_rate / 100:.2%}\n'
    if old.paint != new.paint:
        msg += f'涂墨面积: ({new.paint - old.paint:+}) {new.paint:,}p\n'
    if old.badges != new.badges:
        msg += f'徽章: (+{new.badges - old.badges}) {new.badges}\n'
    if (old.event_gold + old.event_silver + old.event_bronze + old.event_none) != (
            new.event_gold + new.event_silver + new.event_bronze + new.event_none):
        str_event = ''
        if old.event_gold != new.event_gold:
            str_event += f' 🏅️+{new.event_gold - old.event_gold}'
        if old.event_silver != new.event_silver:
            str_event += f' 🥈+{new.event_silver - old.event_silver}'
        if old.event_bronze != new.event_bronze:
            str_event += f' 🥉+{new.event_bronze - old.event_bronze}'
        if old.event_none != new.event_none:
            str_event += f' +{new.event_none - old.event_none}'
        msg += f'活动: {str_event}\n'
    if (old.open_gold + old.open_silver + old.open_bronze + old.open_none) != (
            new.open_gold + new.open_silver + new.open_bronze + new.open_none):
        str_open = ''
        if old.open_gold != new.open_gold:
            str_open += f' 🏅️+{new.open_gold - old.open_gold}'
        if old.open_silver != new.open_silver:
            str_open += f' 🥈+{new.open_silver - old.open_silver}'
        if old.open_bronze != new.open_bronze:
            str_open += f' 🥉+{new.open_bronze - old.open_bronze}'
        if old.open_none != new.open_none:
            str_open += f' +{new.open_none - old.open_none}'
        msg += f'开放: {str_open}\n'

    if old.coop_cnt != new.coop_cnt:
        msg += f'\n打工次数: (+{new.coop_cnt - old.coop_cnt}) {new.coop_cnt}\n'
    if old.coop_gold_egg != new.coop_gold_egg:
        msg += f'金鲑鱼卵: (+{new.coop_gold_egg - old.coop_gold_egg}) {new.coop_gold_egg}\n'
    if old.coop_egg != new.coop_egg:
        msg += f'鲑鱼卵: (+{new.coop_egg - old.coop_egg}) {new.coop_egg}\n'
    if old.coop_boss_cnt != new.coop_boss_cnt:
        msg += f'头目鲑鱼: (+{new.coop_boss_cnt - old.coop_boss_cnt}) {new.coop_boss_cnt}\n'
    if (old.coop_gold + old.coop_silver + old.coop_bronze) != (new.coop_gold + new.coop_silver + new.coop_bronze):
        str_coop = ''
        if old.coop_bronze != new.coop_bronze:
            str_coop += f' 🏅️{new.coop_bronze - old.coop_bronze:+}'
        if old.coop_silver != new.coop_silver:
            str_coop += f' 🥈{new.coop_silver - old.coop_silver:+}'
        if old.coop_gold != new.coop_gold:
            str_coop += f' 🥉{new.coop_gold - old.coop_gold:+}'
        msg += f'鳞片: {str_coop}\n'

    msg = f'```{msg}```'
    # u = get_user(user_id=user_id)
    # if report_day and fst_day and not u.report_type:
    #     msg += f'```\n\n订阅早报: /report```'
    logger.debug(msg)
    return msg


matcher_report_all = on_command("report_all", priority=10, block=True)


@matcher_report_all.handle(parameterless=[Depends(_check_session_handler)])
async def report_all(bot: Bot, event: Event):
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()

    user = dict_get_or_set_user_info(platform, user_id)
    msg = get_report_all_md(user.game_sp_id)
    await bot_send(bot, event, msg)


def get_report_all_md(player_code):
    res = model_get_report_all(player_code)
    if not res:
        return "数据准备中"
    text = ''
    for r in res[:30]:
        _d = r
        last_time = _d.get('last_play_time')
        if last_time:
            last_play_time = datetime.datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S").strftime("%m-%d  %H:%M")
        else:
            last_play_time = ""

        win_rate_change = _d.get('win_rate_change')
        str_win_rate_change = ""
        # if win_rate_change:
        #     if win_rate_change > 0:
        #         str_win_rate_change = f'<span style="color:rgb(255, 148, 157)">+{win_rate_change}</span>'
        #     elif win_rate_change < 0:
        #         str_win_rate_change = f'<span style="color:rgb(96, 58, 255)">{win_rate_change}</span>'
        # else:
        #     str_win_rate_change = 0

        if win_rate_change:
            if win_rate_change > 0:
                str_win_rate_change = f'{win_rate_change}'
            elif win_rate_change < 0:
                str_win_rate_change = f'{win_rate_change}'
        else:
            str_win_rate_change = 0

        text += (f"|{last_play_time}|{_d.get('total_cnt')}|{_d.get('total_inc_cnt')}|{_d.get('win_cnt')}|"
                 f"{_d.get('win_rate')}|{str_win_rate_change}|{_d.get('coop_cnt')}|{_d.get('coop_inc_cnt')}|"
                 f"{_d.get('coop_boss_cnt')}|{_d.get('coop_boss_change')}|"
                 f"{_d.get('rank')}|{_d.get('udemae')}|\n")
    msg = f'''#### 最近30份日报数据如下
|||||||||||||
|---|---|---:|---|---|---:|---|---|---|---|---|---|
|最后游玩时间|总对战|增|胜场|胜率|变化|总打工|增|总boss|增|等级|技术|
{text}'''
    return msg
