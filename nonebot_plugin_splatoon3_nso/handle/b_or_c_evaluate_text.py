import random
import time
from datetime import datetime as dt

from nonebot import logger

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
        my_team_disconnected_count: 我方队伍掉线人数
        other_team_disconnected_count: 对方队伍掉线人数

    Args:
        my_data: 玩家数据字典，包含武器名称等信息
        stats: 统计数据字典，包含上述所有属性对应的字段
    """

    def __init__(self, my_data, stats):
        self.my_data = my_data
        self.my_weapon_name: str = my_data.get('weapon_name', '') if my_data else ''
        self.my_kill = my_data.get('kill', 0) if my_data else 0
        self.my_kd = my_data.get('kd', 0) if my_data else 0
        self.stats = stats

        # 将stats中的每个值解析为类的属性
        # 1.自己队伍是否有金x或银x，且对面没有任何金x银x
        # 值为0表示没有金x银x，1表示有银x，2表示有金x（同时有金和银时优先金）
        self.my_team_has_x_other_team_no_x = stats.get('my_team_has_x_other_team_no_x', 0)
        # 2.对面有金x或银x，自己队伍没有金x银x
        # 值为0表示没有金x银x，1表示有银x，2表示有金x（同时有金和银时优先金）
        self.other_team_has_x_my_team_no_x = stats.get('other_team_has_x_my_team_no_x', 0)
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
        # 15.我方队伍掉线人数
        self.my_team_disconnected_count = stats.get('my_team_disconnected_count', 0)
        # 16.对方队伍掉线人数
        self.other_team_disconnected_count = stats.get('other_team_disconnected_count', 0)

    @staticmethod
    def _select_evaluation(evaluations):
        """从评价语句列表中选择一条满足条件的评价语句

        Args:
            evaluations: 评价语句列表，每个元素包含text、condition和weight字段

        Returns:
            评价语句文本，如果没有满足条件的评价语句则返回空字符串
        """
        # 筛选出满足条件的评价语句
        valid_evaluations = []
        for e in evaluations:
            if e["condition"] is None or (callable(e["condition"]) and e["condition"]()):
                valid_evaluations.append(e)

        # 打印满足条件的评价语句
        # print(f"满足条件的评价语句: {valid_evaluations}")

        # 如果没有满足条件的评价语句，返回空字符串
        if not valid_evaluations:
            return ""

        # 根据权重随机选择评价语句
        weights = [e.get('weight', 1) for e in valid_evaluations]
        selected_evaluation = random.choices(valid_evaluations, weights=weights, k=1)[0]

        # 从选中的评价语句中随机选择一个文本
        if isinstance(selected_evaluation["text"], list):
            text = random.choice(selected_evaluation["text"])
        else:
            text = selected_evaluation["text"]
        logger.info(f'对战评价语为 {text}')
        return text

    def _get_win_evaluations(self, is_clean_sweep=False):
        """获取评价语句及其条件
        :param is_clean_sweep: 是否完胜
        :return: 评价语句
        """
        # 定义所有可能的评价语句及其条件
        evaluations = [
            {"text": ["超绝完胜！！", "YYYYY！！", "你跟队友出色的配合，可以驾驶eva了",
                      "此地图已经完全被你们占领了！"],
             "condition": lambda: is_clean_sweep, "weight": 5},
            {"text": [f"{self.my_weapon_name}大人太强了！！"],
             "condition": lambda: self.i_am_max_kill and self.i_am_max_kd, "weight": 5},
            {"text": ["又躺赢了", "我去完全躺赢", "我们四个太强了！"],
             "condition": lambda: self.i_am_last_contributor, "weight": 5},
            {"text": ["带飞队友咯", "不愧是我，我真是太强了"],
             "condition": lambda: self.i_am_max_kill, "weight": 5},
            {"text": ["绝对的强者，由此而生的孤独，教会你爱的将会是！？"],
             "condition": lambda: self.i_am_max_kill and self.i_am_max_kd and self.my_kill_over_20, "weight": 20},
            {"text": ["老大能加你吗？你上线我上线", "老大请用力地揍我...！", "你不许排我对面……", "有手就行嗷"],
             "condition": lambda: self.i_am_max_kill and not self.my_kd_under_1, "weight": 10},
            {"text": ["太强了，如果你是我队友我会直接穿上婚纱", "太强了，我本来也打算打成这样的"],
             "condition": lambda: self.i_am_max_kill and self.my_kill_over_20, "weight": 10},
            {"text": ["好鱿章法！", "手感好好！", "超鱿型！！！"], "condition": None},
            {"text": [f"kd神!竟然已经{self.my_kd}kd了"], "condition": lambda: self.my_kd_over_5 and self.i_am_max_kd,
             "weight": 20},
            {"text": [f"kill神!竟然已经{self.my_kill}kill了"],
             "condition": lambda: self.my_kill_over_20 and self.i_am_max_kill, "weight": 20},
            {"text": ["你简直是天选海产，竟然全程0死亡"], "condition": lambda: self.i_have_zero_death, "weight": 20},
            {"text": ["看来是相同类型的替身呢！难怪你也这么强"],
             "condition": lambda: self.my_weapon_name.startswith("斯普拉射击枪") and self.my_kill_over_20,
             "weight": 30},
            {"text": ["超解一时爽，一直超解一直爽！！"],
             "condition": lambda: self.my_weapon_name.startswith("可变形滚筒") and self.my_kill_over_20, "weight": 30},
            {"text": [f"{4 - self.my_team_disconnected_count}打4赢了也太强了"],
             "condition": lambda: self.my_team_disconnected_count and not self.other_team_disconnected_count,
             "weight": 90},
            {"text": [
                f"怎么突然变成{4 - self.my_team_disconnected_count}打{4 - self.other_team_disconnected_count}了，好诶"],
                "condition": lambda: self.my_team_disconnected_count and self.other_team_disconnected_count,
                "weight": 50},
            {"text": ["太刺激了，一分险胜", "老大绝境翻盘了喵！"],
             "condition": lambda: self.score_diff_is_1, "weight": 90},
        ]

        return self._select_evaluation(evaluations)

    def process_clean_sweep(self):
        """处理完胜情况"""
        return self._get_win_evaluations(is_clean_sweep=True)

    def process_normal_win(self):
        """处理普通胜利情况"""
        return self._get_win_evaluations(is_clean_sweep=False)

    def process_lose(self):
        """处理失败情况"""
        # 定义所有可能的评价语句及其条件
        evaluations = [
            {"text": ["队友都是气垫，那气垫是什么"],
             "condition": lambda: self.my_weapon_name.startswith("四重弹跳手枪") and self.i_am_max_kill},
            {"text": ["救救我救救我救救我救救我", "elo大人我的春天何时才能到来阿…", "拼尽全力无法战胜", "野人不配赢",
                      "rtt修修你的匹配吧🙏😭🙏😭🙏", "燃尽了………", "太努力了……rtt欠你一把完胜"],
             "condition": lambda: self.i_am_max_kill and self.i_am_first_contributor and self.i_have_three_gold,
             "weight": 50},
            {"text": ["elo大人下把该轮到我赢了吧！", "这能输？", "这对吗？", ],
             "condition": lambda: self.i_am_max_kill, "weight": 5},
            {"text": ["野人少死一点能赢", "野人全责", "拼尽全力无法战胜", "老大没事吧喵", "老大要不去打工吧喵",
                      "拼尽全力无法战胜"],
             "condition": None},
            {"text": ["今天没吃疯狂星期四，打喷没力气"],
             "condition": lambda: self.is_thursday, "weight": 10},
            {"text": ["队友是人吗"],
             "condition": lambda: self.i_am_max_kill and self.my_kill_over_20 and self.i_am_first_contributor and self.i_have_three_gold and self.i_am_max_kd,
             "weight": 90},
            {"text": ["你那金X不如给我戴"],
             "condition": lambda: self.i_am_max_kill and self.my_team_has_x_other_team_no_x == 2, "weight": 20},
            {"text": ["你那银X不如给我戴"],
             "condition": lambda: self.i_am_max_kill and self.my_team_has_x_other_team_no_x == 1, "weight": 20},
            {"text": ["我打金X？真的假的"],
             "condition": lambda: self.other_team_has_x_my_team_no_x == 2, "weight": 20},
            {"text": ["我打银X？真的假的"],
             "condition": lambda: self.other_team_has_x_my_team_no_x == 1, "weight": 20},
            {"text": ["就差一分！！！好气啊！！", "这也能翻盘？"],
             "condition": lambda: self.score_diff_is_1, "weight": 90},
        ]

        # 60%概率使用条件评价，40%概率使用随机借口
        # 设置随机种子，确保外部和ExcuseGenerator内部都使用相同的随机种子
        seed = int(time.time() * 1000)  # 使用当前时间作为随机种子
        random.seed(seed)

        # 保存当前随机种子状态
        seed_state = random.getstate()

        try:
            if random.random() < 0.6:
                evaluation = self._select_evaluation(evaluations)
                # 如果没有满足条件的评价语句，则使用随机借口
                if evaluation:
                    return evaluation
                else:
                    return get_random_excuse(seed)
            else:
                return get_random_excuse(seed)
        finally:
            # 恢复随机种子状态
            random.setstate(seed_state)

    def process_deemed_lose(self):
        """处理自己掉线情况"""
        # 定义所有可能的评价语句及其条件
        evaluations = [
            {"text": ["rtt修修你那破网吧", "哦不，都是rtt的错", "希望别进小黑屋，求求了", "为了我，对rtt使用炎拳吧！"],
             "condition": None},
        ]

        return self._select_evaluation(evaluations)

    def process_exempted_lose(self):
        """处理队友掉线情况，算作失败，但豁免惩罚
        能进入这个函数，self.my_team_disconnected_count必然不为0了"""
        # 定义所有可能的评价语句及其条件
        evaluations = [
            {"text": ["rtt修修你那破网吧", "至少不用扣分了", "不如去打工吧", "难道是有人裸连打喷"],
             "condition": None},
            {"text": [f"{4 - self.my_team_disconnected_count}打4这也太难了",
                      f"{4 - self.my_team_disconnected_count}打4怎么可能赢呢？"],
             "condition": lambda: not self.other_team_disconnected_count, "weight": 4},
            {"text": [
                f"怎么突然变成{4 - self.my_team_disconnected_count}打{4 - self.other_team_disconnected_count}了，rtt全责"],
                "condition": lambda: self.other_team_disconnected_count, "weight": 2},
        ]

        return self._select_evaluation(evaluations)

    def process_draw(self):
        """处理不到一分钟的无效对局"""
        # 定义所有可能的评价语句及其条件
        evaluations = [
            {"text": ["海产嘉宾遗憾离场…", "求别掉", "rtt的土豆服务器太拉了", "rtt在浪费海产的时间！", "不如来跳舞吧～",
                      "不如来一局占斗士吧", "不如去打工吧", "又白打了...."],
             "condition": None},
        ]

        return self._select_evaluation(evaluations)


async def get_evaluate_text(is_battle, detail):
    """
    获取对战评价文本
    :param is_battle: 是否是对战
    :param detail: 对战详情或打工详情
    """
    # 记录开始时间
    # start_time = time.time()

    if not is_battle:
        # 打工，不做评价
        return ""
    if not detail:
        return ""
    # 这里detail是该次对局的 battle详情或coop详情数据
    data = detail.get('data', {})
    detail = data.get('vsHistoryDetail')
    if not detail:
        return ""
    # 排除掉任何祭典对局
    vs_mode = detail.get('vsMode', {})
    mode = vs_mode.get('mode', '')
    if mode == "FEST":
        return ""
    # 排除私房
    if mode == "PRIVATE":
        return ""

    def get_kd(p: dict) -> float:
        """获取kd"""
        # 安全获取result数据
        re = p.get('result') if p else None
        if not re:
            re = {"kill": 0, "death": 0, "assist": 0, "special": 0}
        k = re.get('kill', 0) - re.get('assist', 0)
        d = re.get('death', 0)
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
        # 安全获取result数据
        result = p.get('result') if p else None
        is_disconnected = result is None  # 如果result为None，表示玩家掉线
        if not result:
            result = {"kill": 0, "death": 0, "assist": 0, "special": 0}

        # 安全获取weapon数据
        weapon = p.get('weapon') if p else None
        if not weapon:
            weapon = {"name": "", "id": ""}

        d = {
            "is_gold_x": False,  # 金X
            "is_silver_x": False,  # 银X
            "kd": get_kd(p) if p else 0,  # kd
            "kill": result.get('kill', 0),  # 击杀数(含助攻)
            "death": result.get('death', 0),  # 死亡数
            "weapon_name": weapon.get('name', ''),  # 武器名称
            "weapon_id": weapon.get('id', ''),  # 武器ID
            "is_myself": is_myself,  # 是否是自己
            "is_disconnected": is_disconnected,  # 是否掉线
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
        disconnected_count = 0  # 掉线人数，默认值为0

        for player in team_data:
            # 检查是否有金X (假设数据中有is_gold_x字段或类似标识)
            if player.get('is_gold_x', False):
                has_gold_x = True
            # 检查是否有银X (假设数据中有is_silver_x字段或类似标识)
            if player.get('is_silver_x', False):
                has_silver_x = True

            # 检查是否掉线
            if player.get('is_disconnected', False):
                disconnected_count += 1

            # 计算并更新最高KD (使用player字典中已有的kd值)
            kd = player.get('kd', 0)
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
            'max_kill_is_myself': max_kill_is_myself,
            'disconnected_count': disconnected_count  # 掉线人数
        }

    judgement = detail.get("judgement")  # 比赛结果
    # 处理我方比分，兼容result层可能不存在或为None的情况
    my_team = detail.get("myTeam", {})
    my_result = my_team.get("result") if isinstance(my_team, dict) else None
    my_score = my_result.get("score", 0) if my_result and isinstance(my_result, dict) else 0
    # 处理对方比分，兼容result层可能不存在或为None的情况
    other_teams = detail.get("otherTeams", [])
    other_team = other_teams[0] if other_teams and isinstance(other_teams, list) else {}
    other_result = other_team.get("result") if isinstance(other_team, dict) else None
    other_score = other_result.get("score", 0) if other_result and isinstance(other_result, dict) else 0
    # 我方队伍和地方队伍数据
    my_team_players_list = detail.get("myTeam").get("players")
    other_team_players = detail.get("otherTeams")[0].get("players")

    # 三金牌
    awards = detail.get("awards")
    three_gold_awards = all(award.get("rank") == "GOLD" for award in awards)

    # 队友和对手成绩计算
    my_team_data = [await get_p_data(p=p, is_myself=p.get("isMyself")) for p in my_team_players_list]
    other_team_data = [await get_p_data(p) for p in other_team_players]
    # 我的数据
    my_idx = next((i for i, p in enumerate(my_team_players_list) if p.get("isMyself")), None)
    my_data = next((p for p in my_team_data if p.get("is_myself")), None)
    # 分析两支队伍的数据
    my_team_analysis = analyze_team_data(my_team_data)
    other_team_analysis = analyze_team_data(other_team_data)

    # 统计数据
    def get_battle_statistics():
        """根据队伍数据和个人数据，统计各项指标"""

        # 统计结果字典
        stats = {
            'my_team_has_x_other_team_no_x': 0,  # 1.自己队伍是否有金x或银x，且对面没有任何金x银x（0=无，1=银x，2=金x）
            'other_team_has_x_my_team_no_x': 0,  # 2.对面有金x或银x，自己队伍没有金x银x（0=无，1=银x，2=金x）
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
            'my_kd_under_1': False,  # 14.自己kd是否小于1
            'my_team_disconnected_count': 0,  # 15.我方队伍掉线人数
            'other_team_disconnected_count': 0  # 16.对方队伍掉线人数
        }

        # 1.自己队伍是否有金x或银x，且对面没有任何金x银x
        # 值为0表示没有金x银x，1表示有银x，2表示有金x（同时有金和银时优先金）
        if (my_team_analysis['has_gold_x'] or my_team_analysis['has_silver_x']) and not (
                other_team_analysis['has_gold_x'] or other_team_analysis['has_silver_x']):
            if my_team_analysis['has_gold_x']:
                stats['my_team_has_x_other_team_no_x'] = 2
            else:
                stats['my_team_has_x_other_team_no_x'] = 1

        # 2.对面有金x或银x，自己队伍没有金x银x
        # 值为0表示没有金x银x，1表示有银x，2表示有金x（同时有金和银时优先金）
        if (other_team_analysis['has_gold_x'] or other_team_analysis['has_silver_x']) and not (
                my_team_analysis['has_gold_x'] or my_team_analysis['has_silver_x']):
            if other_team_analysis['has_gold_x']:
                stats['other_team_has_x_my_team_no_x'] = 2
            else:
                stats['other_team_has_x_my_team_no_x'] = 1

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
        if my_data and my_data.get('kd', 0) < 1:
            stats['my_kd_under_1'] = True

        # 15.我方队伍掉线人数
        stats['my_team_disconnected_count'] = my_team_analysis.get('disconnected_count', 0)

        # 16.对方队伍掉线人数
        stats['other_team_disconnected_count'] = other_team_analysis.get('disconnected_count', 0)

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

    # 计算并打印执行时间
    # end_time = time.time()
    # execution_time = end_time - start_time
    # print(f"get_evaluate_text 执行时间: {execution_time:.4f} 秒")

    return evaluate
