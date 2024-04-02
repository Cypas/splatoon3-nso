from datetime import datetime as dt, timedelta
from .send_msg import bot_send
from .utils import _check_session_handler, get_battle_time_or_coop_time
from ..data.data_source import model_get_temp_image_path, dict_get_or_set_user_info
from ..s3s.splatoon import Splatoon
from ..utils.bot import *


@on_command("history", aliases={'his'}, priority=10, block=True).handle(parameterless=[Depends(_check_session_handler)])
async def history(bot: Bot, event: Event, args: Message = CommandArg()):
    """历史记录查询"""
    _type = 'open'
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    cmd_message = args.extract_plain_text().strip()
    logger.debug(f'history: {cmd_message}')
    if cmd_message:
        cmd_lst = cmd_message.split()
        if 'o' in cmd_lst or 'open' in cmd_lst:
            _type = 'open'
        if 'e' in cmd_lst or 'event' in cmd_lst:
            _type = 'event'
        if 'f' in cmd_lst or 'fest' in cmd_lst:
            _type = 'fest'

    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    await bot_send(bot, event, "开始努力作图，请稍等~", skip_log_cmd=True)
    msg = await get_history_md(splatoon, _type=_type)
    # 关闭连接池
    await splatoon.req_client.close()
    await bot_send(bot, event, msg, image_width=1000)


async def get_history_md(splatoon: Splatoon, _type='open'):
    """获取历史记录md文本"""
    logger.info(f'get history {_type}')
    res = None
    try:
        if _type == 'event':
            res = await splatoon.get_event_battles()
        elif _type == 'open':
            res = await splatoon.get_bankara_battles()
        elif _type == 'fest':
            res = await splatoon.get_regular_battles()
    except ValueError as e:
        return "bot网络错误，请稍后再试!"
    if not res:
        return "No battle found!"

    msg = ''
    event_h = []
    if _type == 'event':
        event_h = res['data']['eventBattleHistories']['historyGroups']['nodes']
    if _type == 'open':
        event_h = res['data']['bankaraBattleHistories']['historyGroups']['nodes']
    if _type == 'fest':
        event_h = res['data']['regularBattleHistories']['historyGroups']['nodes']
        new_event_h = []
        for g in event_h:
            for n in g['historyDetails']['nodes']:
                # 单排 fest
                if n['vsMode']['id'] == 'VnNNb2RlLTc=':
                    new_event_h.append(g)
                    break
        event_h = new_event_h

    for g_node in event_h:
        msg += await get_group_node_msg(g_node, splatoon, _type)
        break

    # logger.info(msg)
    if not msg:
        return f'No battle {_type} found!'
    return msg


async def get_group_node_msg(g_node, splatoon, _type):
    msg = ''
    battle_lst = []
    if _type == 'event':
        battle_lst = g_node['historyDetails']['nodes']
        fst_battle = battle_lst[0]
        battle_id = fst_battle['id']
        battle_t = get_battle_time_or_coop_time(battle_id)
        b_t = dt.strptime(battle_t, '%Y%m%dT%H%M%S') + timedelta(hours=8)
        msg = f"#### 活动: {g_node['leagueMatchHistoryGroup']['leagueMatchEvent']['name']} HKT {b_t:%Y-%m-%d %H:%M:%S}\n"
    elif _type == 'open':
        fst_battle = g_node['historyDetails']['nodes'][0]
        battle_id = fst_battle['id']
        battle_t = get_battle_time_or_coop_time(battle_id)
        b_t = dt.strptime(battle_t, '%Y%m%dT%H%M%S') + timedelta(hours=8)
        msg = f"#### 开放: {fst_battle['vsRule']['name']} HKT {b_t:%Y-%m-%d %H:%M:%S}\n"
        battle_lst = []
        stage_lst = []
        for n in g_node['historyDetails']['nodes']:
            if 'bankaraMatch' not in n or 'earnedUdemaePoint' not in n['bankaraMatch']:
                continue
            stage_name = n['vsStage']['name']
            if stage_name not in stage_lst:
                stage_lst.append(stage_name)
            # 最新一个时段
            if len(stage_lst) > 2:
                break
            battle_lst.append(n)
    elif _type == 'fest':
        battle_lst = g_node['historyDetails']['nodes']
        b_lst = []
        for b in battle_lst:
            if b['vsMode']['id'] == 'VnNNb2RlLTc=':
                b_lst.append(b)
        battle_lst = b_lst
        fst_battle = battle_lst[0]
        battle_id = fst_battle['id']
        battle_t = get_battle_time_or_coop_time(battle_id)
        b_t = dt.strptime(battle_t, '%Y%m%dT%H%M%S') + timedelta(hours=8)
        msg = f"#### 祭典单排 HKT {b_t:%Y-%m-%d %H:%M:%S}\n"

    _type_name = ""
    if _type == "event":
        _type_name = "(活动)"
    elif _type == "open":
        _type_name = "(组排)"
    elif _type == "fest":
        _type_name = ""

    msg += f'''
|  |   ||  ||||||||||
| --: |--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|:---------|
|胜负|分数变动{_type_name}|当前分数{_type_name}|武器|总|杀+助|死亡|kd|大招|涂地|耗时|比分|地图|
'''

    dict_p = {}
    last_power = 0
    for b in battle_lst[::-1]:
        _id = b['id']
        dict_p[_id] = {}
        battle_detail = await splatoon.get_battle_detail(_id, multiple=True)
        if not battle_detail:
            battle_detail = await splatoon.get_battle_detail(_id, multiple=True)
            if not battle_detail:
                continue
        cur_power = 0
        if _type == 'event':
            cur_power = battle_detail['data']['vsHistoryDetail']['leagueMatch']['myLeaguePower']
        elif _type == 'open':
            b_d = battle_detail['data']['vsHistoryDetail'].get('bankaraMatch') or {}
            cur_power = (b_d.get('bankaraPower') or {}).get('power')
        elif _type == 'fest':
            b_d = battle_detail['data']['vsHistoryDetail'].get('festMatch') or {}
            cur_power = b_d.get('myFestPower')

        if cur_power:
            dict_p[_id] = {'cur': cur_power, 'diff': cur_power - last_power if last_power else ''}
        last_power = cur_power

        b_detail = battle_detail['data']['vsHistoryDetail']
        my_str = get_my_row(b_detail['myTeam'])
        duration = b_detail['duration']

        score_list = []
        for t in [b_detail['myTeam']] + b_detail['otherTeams']:
            if (t.get('result') or {}).get('score') is not None:
                score_list.append(str((t['result']['score'])))
            elif (t.get('result') or {}).get('paintRatio') is not None:
                score_list.append(f"{t['result']['paintRatio']:.2%}"[:-2])
        score = ':'.join(score_list)
        dict_p[_id].update({'my_str': my_str, 'duration': duration, 'score': score})

    for n in battle_lst:
        _id = n['id']
        if _id not in dict_p:
            continue
        p = dict_p.get(_id) or {}
        if p.get('diff'):
            str_p = f'{p["diff"]:+.2f}|'
        else:
            str_p = '      |'

        if p.get('cur'):
            str_p += f' {p["cur"]:.2f}'
        else:
            str_p += '        '

        my_str = p.get('my_str') or ''
        weapon_img = (((n.get('player') or {}).get('weapon') or {}).get('image') or {}).get('url') or ''

        img_type = "battle_weapon_main"
        weapon_main_img = await model_get_temp_image_path(img_type, n['player']['weapon']['name'], weapon_img)
        if weapon_main_img:
            weapon_str = f'<img height="20" src="{weapon_main_img}"/>'
        else:
            weapon_str = n['player']['weapon']['name']
        duration = p.get('duration') or ''
        score = p.get('score') or ''
        jud = n.get('judgement') or ''
        if jud not in ('WIN', 'LOSE'):
            jud = 'DRAW'
        row = f"|{jud}| {str_p}| {weapon_str}|{my_str}| {duration}s|{score}| {n['vsStage']['name'][:7]}"

        msg += row + '\n'
    msg += '||\n'
    return msg


def get_my_row(my_team):
    p = {}
    for _p in my_team['players']:
        if _p.get('isMyself'):
            p = _p
            break

    re = p['result']
    if not re:
        re = {"kill": 0, "death": 99, "assist": 0, "special": 0}
    ak = re['kill']
    k = re['kill'] - re['assist']
    k_str = f'{k}+{re["assist"]}'
    d = re['death']
    # 避免除数和被除数为0的情况
    if k != 0:
        if d == 0:
            ration = k / 1
        else:
            ration = k / d
    else:
        ration = 0

    t = f"{ak:>2}|{k_str:>5}k| {d:>2}d|{ration:>4.1f}|{re['special']:>3}sp| {p['paint']:>4}p "
    return t
