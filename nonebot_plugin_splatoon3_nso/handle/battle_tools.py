from datetime import datetime as dt, timedelta

from .utils import DICT_RANK_POINT
from ..s3s.splatoon import Splatoon
from ..data.data_source import model_get_top_player, model_get_temp_image_path, model_get_all_weapon, model_get_top_all
from ..utils.bot import *


async def get_b_point_and_process(battle_detail, bankara_match, splatoon: Splatoon = None):
    """获取真格模式挑战点数和挑战进度"""
    try:
        point = 0
        b_process = ''
        if not bankara_match:
            return point, ''

        if bankara_match == 'OPEN':
            # open
            point = battle_detail['bankaraMatch']['earnedUdemaePoint']
            if point > 0:
                point = f'+{point}'
        else:
            # challenge
            bankara_info = await splatoon.get_bankara_battles()
            # 得确定对战位于哪一个group
            battle_id = battle_detail['id']
            groups = bankara_info['data']['bankaraBattleHistories']['historyGroups']['nodes']
            group_idx = get_battle_group_idx(groups, battle_id)

            # 取该组别信息
            hg = bankara_info['data']['bankaraBattleHistories']['historyGroups']['nodes'][group_idx]
            point = hg['bankaraMatchChallenge']['earnedUdemaePoint'] or 0
            bankara_detail = hg['bankaraMatchChallenge'] or {}
            if point > 0:
                point = f'+{point}'
            if point == 0 and bankara_detail and (
                    len(hg['historyDetails']['nodes']) == 1 and
                    bankara_detail.get('winCount') + bankara_detail.get('loseCount') == 1):
                # 挑战第一局比赛，花费点数购买入场券
                udemae = hg[''].get('udemae') or ''
                point = DICT_RANK_POINT.get(udemae[:2], 0)

            win_count = bankara_detail.get('winCount') or 0
            lose_count = bankara_detail.get('loseCount') or 0
            b_process = f"{win_count}胜-{lose_count}负"

    except Exception as e:
        logger.exception(e)
        point = 0
        b_process = ''

    return point, b_process


async def get_x_power_and_process(battle_detail, splatoon: Splatoon):
    """获取x赛分数和挑战进度"""
    try:
        power = ''
        x_process = ''

        x_res = await splatoon.get_x_battles()
        # 得确定对战位于哪一个group
        battle_id = battle_detail['id']
        groups = x_res['data']['xBattleHistories']['historyGroups']['nodes']
        group_idx = get_battle_group_idx(groups, battle_id)

        hg = x_res['data']['xBattleHistories']['historyGroups']['nodes'][group_idx]
        x_info = hg['xMatchMeasurement']
        if x_info['state'] == 'COMPLETED':
            last_x_power = battle_detail['xMatch'].get('lastXPower') or 0
            cur_x_power = x_info.get('xPowerAfter') or 0
            xp = cur_x_power - last_x_power
            power = f'{xp:+.2f} ({cur_x_power:.2f})'
        win_count = x_info.get('winCount') or 0
        lose_count = x_info.get('loseCount') or 0
        x_process = f"{win_count}胜-{lose_count}负"

    except Exception as e:
        logger.exception(e)
        power = ''
        x_process = ''

    return power, x_process


def get_battle_group_idx(groups, battle_id) -> int:
    """真格挑战和x赛模式下如果查询输入了idx，需要再去判断其对战属于哪个group 返回其所在group的index"""
    flag_exit = False  # 多层循环跳出标志
    group_idx = 0
    for g_idx, group in groups.items():
        for b in group['historyDetails']['nodes']:
            if b['id'] == battle_id:
                group_idx = g_idx
                flag_exit = True
                break
        if flag_exit:
            break
    return group_idx


def set_statics(**kwargs):
    # 统计push期间战绩
    try:
        current_statics = kwargs['current_statics']
        judgement = kwargs['judgement']
        point = kwargs['point']
        battle_detail = kwargs['battle_detail']

        played_time = dt.strptime(battle_detail['playedTime'], '%Y-%m-%dT%H:%M:%SZ')
        if played_time < dt.utcnow() - timedelta(minutes=60):
            current_statics['open_power'] = 0
            current_statics['max_open_power'] = 0
            return

        current_statics['TOTAL'] += 1
        current_statics[judgement] += 1
        current_statics['point'] += int(point)

        successive = current_statics['successive']
        if judgement == 'WIN':
            successive = max(successive, 0) + 1
        elif judgement not in ('DRAW',):
            successive = min(successive, 0) - 1
        current_statics['successive'] = successive

        for p in battle_detail['myTeam']['players']:
            if not p.get('isMyself'):
                continue
            if not p.get('result'):
                continue
            current_statics['KA'] += p['result']['kill']
            current_statics['K'] += p['result']['kill'] - p['result']['assist']
            current_statics['A'] += p['result']['assist']
            current_statics['D'] += p['result']['death']
            current_statics['S'] += p['result']['special']
            current_statics['P'] += p['paint']

        logger.debug(f"current_statics: {current_statics}")

    except Exception as e:
        logger.exception(e)


def get_statics(data):
    # 获取push期间战绩
    point = 0
    if data.get('point'):
        point = data['point']

    my_str = ''
    if data.get('KA'):
        k_rate = data.get('K', 0) / data['D'] if data.get('D') else 99
        my_str += f"{data.get('KA', 0)} {data.get('K', 0)}+{data.get('A', 0)}k {data.get('D', 0)}d " \
                  f"{k_rate:.2f} {data.get('S', 0)}sp {data.get('P', 0)}p"

    for k in ('point', 'successive', 'KA', 'K', 'A', 'D', 'S', 'P', 'fest_power', 'open_power', 'max_open_power'):
        if k in data:
            del data[k]

    point = f'+{point}' if point > 0 else point
    point_str = f"Point: {point}p" if point else ''
    lst = sorted([(k, v) for k, v in data.items()], key=lambda x: x[1], reverse=True)
    msg = f"""
Statistics:
```
{', '.join([f'{k}: {v}' for k, v in lst])}
WIN_RATE: {data['WIN'] / data['TOTAL']:.2%}
{point_str}
{my_str}
```
"""
    return msg


async def get_top_all_name(name, player_code):
    """对top all榜单上有名的玩家额外渲染name"""
    top_all = model_get_top_all(player_code)
    if not top_all:
        return name

    row = top_all
    max_power = row.power
    top_str = f'F({max_power})' if row.top_type.startswith('Fest') else f'E({max_power})'
    name = name.replace('`', '&#96;').replace('|', '&#124;')
    name = name.strip() + f' <span style="color:#EE9D59">`{top_str}`</span">'
    if '<img' not in name:
        weapon_id = str(row.weapon_id)
        weapon = model_get_all_weapon() or {}
        if weapon.get(weapon_id):
            img_type = "battle_weapon_main"
            weapon_main_img = await model_get_temp_image_path(img_type, weapon[weapon_id]['name'],
                                                              weapon[weapon_id]['url'])
            name += f"<img height='36px' style='position:absolute;right:5px;margin-top:-6px' src='{weapon_main_img}'/>"
    return name


async def get_top_user(player_code):
    """获取top玩家md信息"""
    top_str = ''
    top_user = model_get_top_player(player_code)
    if top_user:
        _x = 'x' if ':6:' in top_user.top_type else 'X'
        if '-a:' in top_user.top_type:
            top_str = f' <span style="color:#fc0390">{_x}{top_user.rank}</span"><span style="color:red">({top_user.power})</span">'
        else:
            top_str = f' <span style="color:red">{_x}{top_user.rank}({top_user.power})</span">'
        weapon_id = str(top_user.weapon_id)
        weapon = model_get_all_weapon() or {}
        if weapon.get(weapon_id):
            img_type = "battle_weapon_main"
            weapon_main_img = await model_get_temp_image_path(img_type, weapon[weapon_id]['name'],
                                                              weapon[weapon_id]['url'])
            top_str += f"<img height='36px' style='position:absolute;right:5px;margin-top:-6px' src='{weapon_main_img}'/>"
        return top_str
    return top_str
