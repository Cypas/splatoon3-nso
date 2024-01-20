from datetime import datetime as dt, timedelta

from .utils import DICT_RANK_POINT, get_battle_true_id
from ..s3s.splatoon import Splatoon
from ..data.data_source import model_get_top_player, model_get_temp_image_path, model_get_all_weapon, model_get_top_all
from ..utils.bot import *


async def get_b_point_and_process(battle_detail, bankara_match, splatoon: Splatoon = None, idx=0):
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
            if idx == 0:
                group_idx = 0
            else:
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
                udemae = hg['historyDetails']['nodes'][0].get('udemae') or ''
                point = DICT_RANK_POINT.get(udemae[:2], 0)

            win_count = bankara_detail.get('winCount') or 0
            lose_count = bankara_detail.get('loseCount') or 0
            b_process = f"{win_count}胜-{lose_count}负"

    except Exception as e:
        logger.exception(e)
        point = 0
        b_process = ''

    return point, b_process


async def get_x_power_and_process(battle_detail, splatoon: Splatoon, idx=0):
    """获取x赛分数和挑战进度"""
    try:
        power = ''
        x_process = ''

        x_res = await splatoon.get_x_battles()
        # 得确定对战位于哪一个group
        if idx == 0:
            group_idx = 0
        else:
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
    battle_true_id = get_battle_true_id(battle_id)
    for g_idx, group in enumerate(groups):
        for b in group['historyDetails']['nodes']:
            if get_battle_true_id(b['id']) == battle_true_id:
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
        return name, 0

    # 有分数记录，去掉好友头像, 高优先级显示分数的武器而不是头像
    if '<img' in name:
        origin_name = name.split('style="color:skyblue">')[-1].split(" <img height='36px'")[0]
        name = f'<span style="color:skyblue">{origin_name}</span>'

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
    return name, float(max_power or 0)


async def get_top_user(player_code):
    """获取top玩家md信息"""
    _power = 0
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
        return top_str, float(top_user.power or 0)
    return top_str, _power


class PushBattleStatistics:
    """推送期间对战统计"""

    def __init__(self):
        self.is_alive = False
        self.total = 0
        self.win = 0
        self.lose = 0
        self.draw = 0
        self.ka = 0
        self.k = 0
        self.a = 0
        self.d = 0
        self.s = 0
        self.p = 0  # 涂地面积
        self.b_point_change = 0  # 蛮颓分数变动
        self.x_point_change = 0  # x赛分数变动
        self.successive = 0  # 连胜/连负
        self.fest_power = 0  # 目前未使用
        self.open_power = 0  # 开放分数，在battle处理过程中外部赋值
        self.max_open_power = 0  # 最高开放分数，在battle处理过程中外部赋值


class PushCoopStatistics:
    """推送期间打工统计"""

    def __init__(self):
        self.is_alive = False
        self.total = 0
        self.win = 0
        self.w1_lose = 0  # w1失败
        self.w2_lose = 0
        self.w3_lose = 0
        self.draw = 0
        self.lv_change: [str] = []
        self.boss = 0
        self.boss_name = ""
        self.boss_kill = 0
        self.gold = 0
        self.silver = 0
        self.bronze = 0


class PushStatistics:
    """推送期间总统计"""

    def __init__(self):
        self.battle = PushBattleStatistics()
        self.coop = PushCoopStatistics()

    def set_battle_st(self, battle_detail, point):
        """更新对战统计"""
        try:
            # 去除超过1h之前的对战数据
            played_time = dt.strptime(battle_detail['playedTime'], '%Y-%m-%dT%H:%M:%SZ')
            if played_time < dt.utcnow() - timedelta(minutes=60):
                return

            b = self.battle
            b.is_alive = True

            # 场次计算
            b.total += 1
            judgement = battle_detail['judgement']
            # judgement有五种情况: "LOSE" | "WIN" | "DEEMED_LOSE" | "EXEMPTED_LOSE" | "DRAW"
            match judgement:
                case "WIN":
                    b.win += 1
                    b.successive = max(b.successive, 0) + 1
                case "LOSE" | "DEEMED_LOSE" | "EXEMPTED_LOSE":
                    b.lose += 1
                    b.successive = min(b.successive, 0) - 1
                case "DRAW":
                    b.draw += 1
            # 点数/power变更
            bankara_match = (battle_detail.get('bankaraMatch') or {}).get('mode') or ''
            if bankara_match:
                # 蛮颓点数
                b.b_point_change += int(point)
            elif battle_detail.get('xMatch'):
                # x赛
                b.x_point_change += int(point)

            # 统计个人kda
            for p in battle_detail['myTeam']['players']:
                if not p.get('isMyself'):
                    continue
                if not p.get('result'):
                    continue
                b.ka += p['result']['kill']
                b.k += p['result']['kill'] - p['result']['assist']
                b.a += p['result']['assist']
                b.d += p['result']['death']
                b.s += p['result']['special']
                b.p += p['paint']

        except Exception as e:
            logger.exception(e)

    def set_coop_st(self, coop_detail):
        """更新打工统计"""
        try:
            # 去除超过1h之前的打工数据
            played_time = dt.strptime(coop_detail['playedTime'], '%Y-%m-%dT%H:%M:%SZ')
            if played_time < dt.utcnow() - timedelta(minutes=60):
                return

            c = self.coop
            c.is_alive = True

            # 统计场数
            c.total += 1
            result_wave = coop_detail["resultWave"]
            match result_wave:
                case -1:
                    c.draw += 1
                case 0:
                    c.win += 1
                case 1:
                    c.w1_lose += 1
                case 2:
                    c.w2_lose += 1
                case 3:
                    c.w3_lose += 1

            # boss 金银铜鳞片
            c.boss_name = coop_detail['boss']['name']
            if coop_detail.get('bossResult'):
                c.boss += 1
                scale = coop_detail.get('scale')
                if scale:
                    c.gold += int(scale.get("gold", 0))
                    c.silver += int(scale.get("silver", 0))
                    c.bronze += int(scale.get("bronze", 0))
                if coop_detail['bossResult']['hasDefeatBoss']:
                    c.boss_kill += 1

            # 段位变更
            if coop_detail.get('afterGrade'):
                # 传说40
                lv = f"{coop_detail['afterGrade']['name']}{coop_detail['afterGradePoint']}"
                c.lv_change.append(lv)

        except Exception as e:
            logger.exception(e)

    def get_battle_st_msg(self) -> str:
        """获取对战统计文本"""
        b = self.battle
        if not b.is_alive:
            # 没有数据
            return ""

        msg = "对战数据统计:\n```\n"
        if not b.total:
            return ""
        else:
            # 场数
            msg += f"总场数：{b.total}，"
            msg += f"胜：{b.win}，"
            msg += f"负：{b.lose}，"
            if b.draw:
                msg += f"无效：{b.draw}，"

            if b.win:
                win_rate = b.win / (b.win + b.lose)
            else:
                win_rate = 0
            msg += f" 胜率：{win_rate:.2%}，"
            msg += "\n"
            # 分数
            if b.b_point_change:
                if b.b_point_change >= 0:
                    b_point_change_str = f"+{b.b_point_change}分"
                else:
                    b_point_change_str = f"{b.b_point_change}分"
                msg += f"蛮颓分数变更：{b_point_change_str}\n"
            if b.x_point_change:
                if b.x_point_change >= 0:
                    x_point_change_str = f"+{b.x_point_change}分"
                else:
                    x_point_change_str = f"{b.x_point_change}分"
                msg += f"x赛分数变更：{x_point_change_str}\n"
            if b.open_power:
                msg += f"开放/活动组队 分数：{b.open_power:.2f},"
                if b.max_open_power:
                    msg += f"最高分数：{b.max_open_power:.2f}\n"
            # 击杀
            # kd比  避免除数和被除数为0的情况
            if b.d == 0:
                b.d = 1
            if b.k != 0 and b.d != 0:
                k_rate = b.k / b.d
            else:
                k_rate = 0
            msg += f"总击杀：{b.ka}，"
            msg += f"击杀：{b.k}，"
            msg += f"助攻：{b.a}，"
            msg += f"死亡：{b.d}，"
            msg += f"kd比：{k_rate:.2f}，"
            msg += f"大招：{b.s}，"
            msg += f"涂地面积：{b.p}p，"
        msg += "\n```\n"

        return msg

    def get_coop_st_msg(self) -> str:
        """获取打工统计文本"""
        c = self.coop
        if not c.is_alive:
            # 没有数据
            return ""

        msg = "打工数据统计:\n```\n"
        if not c.total:
            return ""
        else:
            # 场数
            msg += f"总场数：{c.total}，"
            msg += f"胜：{c.win}，"
            if c.w1_lose:
                msg += f"w1失败：{c.w1_lose}，"
            if c.w2_lose:
                msg += f"w2失败：{c.w2_lose}，"
            if c.w3_lose:
                msg += f"w3失败：{c.w3_lose}，"
            if c.draw:
                msg += f"掉线：{c.draw}，"

            msg += "\n"
            # 分数
            if len(c.lv_change) > 0:
                msg += f"打工等级变更：{c.lv_change[0]} -> {c.lv_change[-1]}\n"
            # boss 金银牌
            if c.boss:
                msg += f"{c.boss_name}：出现{c.boss}，击杀{c.boss_kill}\n"
                msg += f"金鳞片：{c.gold}，"
                msg += f"银鳞片：{c.silver}，"
                msg += f"铜鳞片：{c.bronze}，"
                msg += "\n"

        msg += "```"

        return msg
