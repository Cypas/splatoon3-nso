import random
from datetime import datetime as dt

from .utils import get_game_sp_id_and_name
from ..data.data_source import model_get_top_player
from ..utils.excuse_generator import get_random_excuse


class BattleResultProcessor:
    """对战结果处理器，根据不同情况生成评价

    这个类根据对战结果和统计数据生成相应的评价文本。

    Attributes:
        my_data: 玩家数据字典，包含武器名称等信息
        my_weapon_name: 玩家使用的武器名称
        my_kill: 玩家的击杀数
        my_kd: 玩家的KD值
        stats: 统计数据字典

        # 战斗统计数据属性
        my_team_has_x_other_team_no_x: 自己队伍是否有金x或银x，且对面没有任何金x银x
        other_team_has_x_my_team_no_x: 对面有金x或银x，自己队伍没有金x银x
        my_kd_over_5: 自己队伍以及自己在内kd是否超过5
        i_am_max_kd: 最高kd是否是自己
        my_kill_over_20: 自己队伍以及自己在内最高kill是否超过20
        i_am_max_kill: 最高kill是否是自己
        i_have_three_gold: 自己是否三金
        other_team_max_kill_over_20: 对面最高kill是否超过20
        i_am_first_contributor: 自己贡献是否是第一，即my_idx是否为0
        i_am_last_contributor: 自己贡献是否是第4，即my_idx是否为3
        i_have_zero_death: 自己是否0死亡，my_d为0
        score_diff_is_1: 我方队伍分数和对方分数相差数值为1且不为0
        is_thursday: 今天是否是星期四
        my_kd_under_1: 自己kd是否小于1

    Args:
        my_data: 玩家数据字典，包含武器名称等信息
        stats: 统计数据字典，包含上述所有属性对应的字段
    """

    def __init__(self, my_data, stats):
        self.my_data = my_data
        self.my_weapon_name = my_data.get('weapon_name', '')
        self.my_kill = my_data.get('kill', 0)
        self.my_kd = my_data.get('kd', 0)
        self.stats = stats

        # 将stats中的每个值解析为类的属性
        # 1.自己队伍是否有金x或银x，且对面没有任何金x银x
        self.my_team_has_x_other_team_no_x = stats.get('my_team_has_x_other_team_no_x', False)
        # 2.对面有金x或银x，自己队伍没有金x银x
        self.other_team_has_x_my_team_no_x = stats.get('other_team_has_x_my_team_no_x', False)
        # 3.自己队伍以及自己在内kd是否超过5
        self.my_kd_over_5 = stats.get('my_kd_over_5', False)
        # 4.最高kd是否是自己
        self.i_am_max_kd = stats.get('i_am_max_kd', False)
        # 5.自己队伍以及自己在内最高kill是否超过20
        self.my_kill_over_20 = stats.get('my_kill_over_20', False)
        # 6.最高kill是否是自己
        self.i_am_max_kill = stats.get('i_am_max_kill', False)
        # 7.自己是否三金
        self.i_have_three_gold = stats.get('i_have_three_gold', False)
        # 8.对面最高kill是否超过20
        self.other_team_max_kill_over_20 = stats.get('other_team_max_kill_over_20', False)
        # 9.自己贡献是否是第一，即my_idx是否为0
        self.i_am_first_contributor = stats.get('i_am_first_contributor', False)
        # 10.自己贡献是否是第4，即my_idx是否为3
        self.i_am_last_contributor = stats.get('i_am_last_contributor', False)
        # 11.自己是否0死亡，my_d为0
        self.i_have_zero_death = stats.get('i_have_zero_death', False)
        # 12.我方队伍分数和对方分数相差数值为1且不为0
        self.score_diff_is_1 = stats.get('score_diff_is_1', False)
        # 13.今天是否是星期四
        self.is_thursday = stats.get('is_thursday', False)
        # 14.自己kd是否小于1
        self.my_kd_under_1 = stats.get('my_kd_under_1', False)

    def _get_win_evaluations(self, is_clean_sweep=False):
        """获取评价语句及其条件
        :param is_clean_sweep: 是否完胜
        :return: 评价语句
        """
        # 定义所有可能的评价语句及其条件
        evaluations = [
            {"text": "超鱿型！！！", "condition": lambda: is_clean_sweep},
            {"text": "超绝完胜！！", "condition": lambda: is_clean_sweep},
            {"text": "YYYYY！！", "condition": lambda: is_clean_sweep},
            {"text": f"{self.weapon_name}大人太强了！！", "condition": lambda: self.i_am_max_kill and self.i_am_max_kd},
            {"text": "又躺赢了", "condition": lambda: self.i_am_last_contributor},
            {"text": "我去完全躺赢", "condition": lambda: self.i_am_last_contributor},
            {"text": "带飞队友", "condition": lambda: self.i_am_max_kill},
            {"text": "我们四个太强了！", "condition": lambda: self.i_am_last_contributor},
            {"text": "绝对的强者，由此而生的孤独，教会你爱的将会是！？",
             "condition": lambda: self.i_am_max_kill and self.i_am_max_kd and self.my_kill_over_20},
            {"text": "老大能加你吗？你上线我下线", "condition": lambda: self.i_am_max_kill and not self.my_kd_under_1},
            {"text": "老大请用力地揍我...！", "condition": lambda: self.i_am_max_kill and not self.my_kd_under_1},
            {"text": "你不许排我对面……", "condition": lambda: self.i_am_max_kill and not self.my_kd_under_1},
            {"text": "太强了，如果你是我队友我会直接穿上婚纱",
             "condition": lambda: self.i_am_max_kill and self.my_kill_over_20},
            {"text": "太强了，我本来也打算打成这样的",
             "condition": lambda: self.i_am_max_kill and self.my_kill_over_20},
            {"text": "有手就行嗷", "condition": lambda: self.i_am_max_kill and not self.my_kd_under_1},
            {"text": "好鱿章法！", "condition": None},
            {"text": "手感好好！", "condition": None},
            {"text": "你跟队友出色的配合，可以驾驶eva了", "condition": lambda: is_clean_sweep},
            {"text": "此地图已经完全被你们占领了！", "condition": lambda: is_clean_sweep},
        ]

        # 筛选出满足条件的评价语句
        valid_evaluations = [e for e in evaluations if
                             e["condition"] is None or (callable(e["condition"]) and e["condition"]())]

        # 如果有满足条件的评价语句，随机选择一条
        if valid_evaluations:
            return random.choice(valid_evaluations)["text"]

        # 如果没有满足条件的评价语句，返回空字符串
        return ""

    def process_clean_sweep(self):
        """处理完胜情况"""
        return self._get_win_evaluations(is_clean_sweep=True)

    def process_normal_win(self):
        """处理普通胜利情况"""
        return self._get_win_evaluations(is_clean_sweep=False)

    def process_lose(self):
        """处理失败情况"""
        # 输了编造借口
        return get_random_excuse()

    def process_deemed_lose(self):
        """处理自己掉线情况"""
        deemed_lose_dict = [
            "任天堂修修你那破网吧",
        ]
        return random.choice(deemed_lose_dict)

    def process_exempted_lose(self):
        """处理队友掉线情况"""
        exempted_lose_dict = [
            "任天堂修修你那破网吧",
        ]
        return random.choice(exempted_lose_dict)

    def process_draw(self):
        """处理平局情况"""
        # DRAW：无效比赛
        return ""


async def get_evaluate_text(is_battle, detail):
    """
    获取对战评价文本
    :param is_battle: 是否是对战
    :param detail: 对战详情或打工详情
    """
    if not is_battle:
        # 打工，不做评价
        return ""
    if not detail:
        return ""
    # 这里detail是该次对局的 battle详情或coop详情数据
    detail = detail['data']['vsHistoryDetail']
    # 排除掉任何祭典对局
    mode = detail['vsMode']['mode']
    if mode == "FEST":
        return ""

    def get_kd(p: dict) -> float:
        """获取kd"""
        re = p['result']
        if not re:
            re = {"kill": 0, "death": 0, "assist": 0, "special": 0}
        k = re['kill'] - re['assist']
        d = re['death']
        # 避免除数和被除数为0的情况
        if k != 0:
            if d == 0:
                ration = k / 1
            else:
                ration = k / d
        else:
            ration = 0
        return round(ration, 1)

    async def get_p_data(p: dict, is_myself: bool = False) -> dict:
        """对每个成员进行分析，取成员的数据字典
        """
        d = {
            "is_gold_x": False,  # 金X
            "is_silver_x": False,  # 银X
            "kd": get_kd(p),  # kd
            "kill": p['result']['kill'],  # 击杀数(含助攻)
            "death": p['result']['death'],  # 击杀数(含助攻)
            "weapon_name": p["weapon"]["name"],
            "weapon_id": p["weapon"]["id"],
            "is_myself": is_myself,  # 是否是自己
        }
        player_code, player_name = get_game_sp_id_and_name(p)
        # X 五百强分数
        top_user = model_get_top_player(player_code)
        if top_user:
            rank = top_user.rank
            power = top_user.power
            if rank <= 10:
                d["is_gold_x"] = True
            elif rank <= 500:
                d["is_silver_x"] = True
        return d

    def analyze_team_data(team_data):
        """分析队伍数据，返回金X、银X、最高KD和最高击杀数"""
        has_gold_x = False
        has_silver_x = False
        max_kd = 0
        max_kill = 0
        max_kd_is_myself = False
        max_kill_is_myself = False

        for player in team_data:
            # 检查是否有金X (假设数据中有is_gold_x字段或类似标识)
            if player.get('is_gold_x', False):
                has_gold_x = True
            # 检查是否有银X (假设数据中有is_silver_x字段或类似标识)
            if player.get('is_silver_x', False):
                has_silver_x = True

            # 计算并更新最高KD (假设数据中有kill和death字段)
            if player.get('death', 0) > 0:
                kd = player.get('kill', 0) / player.get('death', 1)
                if kd > max_kd:
                    max_kd = kd
                    max_kd_is_myself = player.get('is_myself', False)

            # 更新最高击杀数
            if player.get('kill', 0) > max_kill:
                max_kill = player.get('kill', 0)
                max_kill_is_myself = player.get('is_myself', False)

        return {
            'has_gold_x': has_gold_x,
            'has_silver_x': has_silver_x,
            'max_kd': round(max_kd, 1),
            'max_kill': max_kill,
            'max_kd_is_myself': max_kd_is_myself,
            'max_kill_is_myself': max_kill_is_myself
        }

    judgement = detail.get("judgement")  # 比赛结果
    my_score = detail.get("myTeam").get("result").get("score", 0)  # 我方比分
    other_score = detail.get("otherTeams")[0].get("result").get("score", 0)  # 对方比分
    # 我方队伍和地方队伍数据
    my_team_players_list = detail.get("myTeam").get("players")
    other_team_players = detail.get("otherTeams").get("players")

    # 三金牌
    awards = detail.get("awards")
    three_gold_awards = all(award.get("rank") == "GOLD" for award in awards)

    # 队友和对手成绩计算
    my_team_data = [await get_p_data(p=p, is_myself=p.get("isMyself")) for p in my_team_players_list]
    other_team_data = [await get_p_data(p) for p in other_team_players]
    # 我的数据
    my_idx = next((i for i, p in enumerate(my_team_players_list) if p.get("isMyself")), None)
    my_data = next((p for p in my_team_data if p.get("is_myself")), None)
    my_weapon_name = my_data.get("weapon_name")  # 武器名
    # 分析两支队伍的数据
    my_team_analysis = analyze_team_data(my_team_data)
    other_team_analysis = analyze_team_data(other_team_data)

    # 统计数据
    def get_battle_statistics():
        """根据队伍数据和个人数据，统计各项指标"""

        # 统计结果字典
        stats = {
            'my_team_has_x_other_team_no_x': False,  # 1.自己队伍是否有金x或银x，且对面没有任何金x银x
            'other_team_has_x_my_team_no_x': False,  # 2.对面有金x或银x，自己队伍没有金x银x
            'my_kd_over_5': False,  # 3.自己队伍以及自己在内kd是否超过5
            'i_am_max_kd': False,  # 4.最高kd是否是自己
            'my_kill_over_20': False,  # 5.自己队伍以及自己在内最高kill是否超过20
            'i_am_max_kill': False,  # 6.最高kill是否是自己
            'i_have_three_gold': False,  # 7.自己是否三金
            'other_team_max_kill_over_20': False,  # 8.对面最高kill是否超过20
            'i_am_first_contributor': False,  # 9.自己贡献是否是第一，即my_idx是否为0
            'i_am_last_contributor': False,  # 10.自己贡献是否是第4，即my_idx是否为3
            'i_have_zero_death': False,  # 11.自己是否0死亡，my_d为0
            'score_diff_is_1': False,  # 12.我方队伍分数和对方分数相差数值为1
            'is_thursday': False,  # 13.今天是否是星期四,0是周一，3是周四
            'my_kd_under_1': False  # 14.自己kd是否小于1
        }

        # 1.自己队伍是否有金x或银x，且对面没有任何金x银x
        if (my_team_analysis['has_gold_x'] or my_team_analysis['has_silver_x']) and not (
                other_team_analysis['has_gold_x'] or other_team_analysis['has_silver_x']):
            stats['my_team_has_x_other_team_no_x'] = True

        # 2.对面有金x或银x，自己队伍没有金x银x
        if (other_team_analysis['has_gold_x'] or other_team_analysis['has_silver_x']) and not (
                my_team_analysis['has_gold_x'] or my_team_analysis['has_silver_x']):
            stats['other_team_has_x_my_team_no_x'] = True

        # 3.自己队伍以及自己在内kd是否超过5
        if my_team_analysis['max_kd'] > 5:
            stats['my_kd_over_5'] = True

        # 4.最高kd是否是自己
        if my_team_analysis['max_kd_is_myself']:
            stats['i_am_max_kd'] = True

        # 5.自己队伍以及自己在内最高kill是否超过20
        if my_team_analysis['max_kill'] > 20:
            stats['my_kill_over_20'] = True

        # 6.最高kill是否是自己
        if my_team_analysis['max_kill_is_myself']:
            stats['i_am_max_kill'] = True

        # 7.自己是否三金
        if three_gold_awards:
            stats['i_have_three_gold'] = True

        # 8.对面最高kill是否超过20
        if other_team_analysis['max_kill'] > 20:
            stats['other_team_max_kill_over_20'] = True

        # 9.自己贡献是否是第一，即my_idx是否为0
        if my_idx == 0:
            stats['i_am_first_contributor'] = True

        # 10.自己贡献是否是第4，即my_idx是否为3
        if my_idx == 3:
            stats['i_am_last_contributor'] = True

        # 11.自己是否0死亡，my_d为0
        if my_data and my_data.get('death', 0) == 0:
            stats['i_have_zero_death'] = True

        # 12.我方队伍分数和对方分数相差数值为1且不为0
        if my_score and other_score and abs(my_score - other_score) == 1:
            stats['score_diff_is_1'] = True

        # 13.今天是否是星期四,0是周一，3是周四
        if dt.now().weekday() == 3:
            stats['is_thursday'] = True

        # 14.自己kd是否小于1
        if my_data and my_data.get('death', 0) > 0:
            my_kd = my_data.get('kill', 0) / my_data.get('death', 1)
            if my_kd < 1:
                stats['my_kd_under_1'] = True

        return stats

    # 获取统计数据
    battle_status = get_battle_statistics()
    # 创建结果处理器实例
    result_processor = BattleResultProcessor(my_data, battle_status)

    # judgement有五种情况: "LOSE" | "WIN" | "DEEMED_LOSE" | "EXEMPTED_LOSE" | "DRAW"
    evaluate = ""
    match judgement:
        case "WIN":
            if my_score == 100:  # 完胜
                evaluate = result_processor.process_clean_sweep()
            else:
                # 普通胜利
                evaluate = result_processor.process_normal_win()
        case "LOSE":
            evaluate = result_processor.process_lose()
        case "DEEMED_LOSE":
            evaluate = result_processor.process_deemed_lose()
        case "EXEMPTED_LOSE":
            evaluate = result_processor.process_exempted_lose()
        case "DRAW":
            evaluate = result_processor.process_draw()

    return evaluate
