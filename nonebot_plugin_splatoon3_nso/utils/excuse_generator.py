import random
import csv
from collections import defaultdict

from .utils import DIR_RESOURCE


class ExcuseGenerator:
    def __init__(self, csv_path=None, seed=None):
        """
        初始化借口生成器，可选择从CSV文件加载借口或使用默认借口库
        参数:
            csv_path: 可选，CSV文件的路径，用于加载自定义借口
            seed: 可选，随机数种子，用于确保结果可重现
        neutral decorations -> person & object
        """
        if seed is not None:
            random.seed(seed)  # 设置随机种子以确保结果可重现

        self.excuse_dict = defaultdict(list)  # 使用defaultdict存储各类借口，默认值为空列表

        if csv_path:
            self.load_csv(csv_path)  # 如果提供了CSV文件路径，则从文件加载借口
        else:
            # if no csv then use default dict
            self.excuse_dict["special"] = [
                "声音听不清", "手柄有延迟", "手柄漂移", "游戏掉帧",
                "我太困了", "我太累了", "手机响了", "猫跳键盘了", "网络太卡",
                "椅子太硬了", "桌子太晃了", "耳机坏了", "屏幕看不清", "太累反应有点慢了",
            ]

            self.excuse_dict["positive_person_nouns"] = ["对面"]
            self.excuse_dict["positive_person_decorations"] = [
                "有点厉害", "运气真好", "真阴", "有小代", "有点准", "真能苟", "真卡",
            ]

            self.excuse_dict["positive_object_nouns"] = ["对面武器", "对面配合", ]
            self.excuse_dict["positive_object_decorations"] = ["真恶心", ]

            self.excuse_dict["positive_neutral_decorations"] = ["真恶心"]

            self.excuse_dict["negative_person_nouns"] = ["队友"]
            self.excuse_dict["negative_person_decorations"] = [
                "太弱", "在干嘛？", "跟不上", "没意识", "太慢", "太烂", "太猥琐",
                "真能送", "乱跑", "瞎打", "不敢冲", "菜逼", "漏人了", "啥比啊"
            ]

            self.excuse_dict["negative_object_nouns"] = [
                "网络", "我们配合", "灵敏度", "游戏", "地图", "手感", "乱数", "武器平衡",
            ]
            self.excuse_dict["negative_object_decorations"] = [
                "太差", "有问题", "不好", "不行", "有点离谱"
            ]

            self.excuse_dict["negative_neutral_decorations"] = ["真恶心", "真垃圾", ]

        positive_prob_weight = 1
        neutral_prob_weight = 1
        person_prob_weight = 1
        obejct_prob_weight = 1

        self.num_special = len(self.excuse_dict["special"])
        self.num_person_pos = len(self.excuse_dict["positive_person_nouns"]) * (
                    len(self.excuse_dict["positive_person_decorations"]) + len(
                self.excuse_dict["positive_neutral_decorations"]))
        self.num_obj_pos = len(self.excuse_dict["positive_object_nouns"]) * (
                    len(self.excuse_dict["positive_object_decorations"]) + len(
                self.excuse_dict["positive_neutral_decorations"]))
        self.num_person_neg = len(self.excuse_dict["negative_person_nouns"]) * (
                    len(self.excuse_dict["negative_person_decorations"]) + len(
                self.excuse_dict["negative_neutral_decorations"]))
        self.num_obj_neg = len(self.excuse_dict["negative_object_nouns"]) * (
                    len(self.excuse_dict["negative_object_decorations"]) + len(
                self.excuse_dict["negative_neutral_decorations"]))

        self.num_neutral = len(self.excuse_dict["positive_neutral_decorations"]) * (
                    len(self.excuse_dict["positive_person_nouns"]) + len(
                self.excuse_dict["positive_object_nouns"])) + len(self.excuse_dict["negative_neutral_decorations"]) * (
                                       len(self.excuse_dict["negative_person_nouns"]) + len(
                                   self.excuse_dict["negative_object_nouns"]))

        total_combinations = self.num_special + self.num_person_pos + self.num_obj_pos + self.num_person_neg + self.num_obj_neg

        self.positive_prob = positive_prob_weight * (self.num_person_pos + self.num_obj_pos) / total_combinations
        self.neutral_prob = neutral_prob_weight * self.num_neutral / total_combinations

        self.person_prob = person_prob_weight * (self.num_person_pos + self.num_person_neg) / total_combinations
        self.object_prob = obejct_prob_weight * (self.num_obj_pos + self.num_obj_neg) / total_combinations

        # print(f'positive_prob: {self.positive_prob:.2f}, neutral_prob: {self.neutral_prob:.2f}')
        # print(f'person_prob: {self.person_prob:.2f}, object_prob: {self.object_prob:.2f}, special_prob: {1-self.person_prob-self.object_prob:.2f}')
        # print(f'total_combinations: {total_combinations}, num_special:{self.num_special}, num_person_pos: {self.num_person_pos}, num_obj_pos: {self.num_obj_pos}, num_person_neg: {self.num_person_neg}, num_obj_neg: {self.num_obj_neg}')

    def load_csv(self, path):
        """
        从CSV文件加载借口数据
        参数:
            path: CSV文件的路径
        """
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            for row in reader:
                cat = row["category"].strip()
                word = row["word"].strip()
                if cat and word:
                    self.excuse_dict[cat].append(word)

    def make_special(self) -> list:
        """
        生成特殊类型的借口
        
        Returns:
            list: 返回一个包含两个元素的列表：
                - 第一个元素: 字符串 "special" 表示类别
                - 第二个元素: 特殊借口文本字符串（如"声音听不清"、"网络太卡"）
        """
        return [f"special", random.choice(self.excuse_dict["special"])]

    def make_person_excuse(self) -> list:
        """
        生成与人物相关的借口
        
        Returns:
            list: 返回一个包含两个元素的列表：
                - 第一个元素: 字符串 "positive" 或 "negative" 表示类别
                - 第二个元素: 针对人的借口文本字符串（如"队友太弱"、"对面有点厉害"）
        """
        noun_prob = random.random()  # return random a number (0, 1)
        word_prob = random.random()
        cat = []
        if noun_prob < self.positive_prob:
            noun = random.choice(self.excuse_dict["positive_person_nouns"])
            if word_prob < self.neutral_prob:
                word = random.choice(self.excuse_dict["positive_neutral_decorations"])
            else:
                word = random.choice(self.excuse_dict["positive_person_decorations"])
            cat.append('positive')
        else:
            noun = random.choice(self.excuse_dict["negative_person_nouns"])
            if word_prob < self.neutral_prob:
                word = random.choice(self.excuse_dict["negative_neutral_decorations"])
            else:
                word = random.choice(self.excuse_dict["negative_person_decorations"])
            cat.append('negative')

        s = ''.join(cat)
        return [s, f"{noun}{word}"]

    def make_object_excuse(self) -> list:
        """
        生成与事物相关的借口
        
        Returns:
            list: 返回一个包含两个元素的列表：
                - 第一个元素: 字符串 "positive" 或 "negative" 表示类别
                - 第二个元素: 针对事物的借口文本字符串（如"网络太差"、"对面武器真恶心"）
        """
        noun_prob = random.random()
        word_prob = random.random()
        cat = []
        if noun_prob < self.positive_prob:
            noun = random.choice(self.excuse_dict["positive_object_nouns"])
            if word_prob < self.neutral_prob:
                word = random.choice(self.excuse_dict["positive_neutral_decorations"])
            else:
                word = random.choice(self.excuse_dict["positive_object_decorations"])
            cat.append('positive')
        else:
            noun = random.choice(self.excuse_dict["negative_object_nouns"])
            if word_prob < self.neutral_prob:
                word = random.choice(self.excuse_dict["negative_neutral_decorations"])
            else:
                word = random.choice(self.excuse_dict["negative_object_decorations"])
            cat.append('negative')

        s = ''.join(cat)
        return [s, f"{noun}{word}"]

    def generate(self) -> list:
        """
        随机生成一个借口
        
        Returns:
            list: 返回一个包含两个元素的列表：
                - 第一个元素: 字符串 "special"、"positive" 或 "negative" 表示类别
                - 第二个元素: 借口文本字符串
        """
        cat_prob = random.random()
        if cat_prob < self.person_prob:
            result = self.make_person_excuse()
        elif cat_prob < self.person_prob + self.object_prob:
            result = self.make_object_excuse()
        else:
            result = self.make_special()
        return result


# 借口生成器实例缓存
_excuse_generator = None


def get_random_excuse():
    """
    快速获取一个随机借口

    Returns:
        str: 返回一个随机生成的借口文本字符串

    Example:
        >>> excuse = get_random_excuse()
        >>> print(excuse)
        "队友太弱"
    """
    global _excuse_generator

    # 首次调用时初始化借口生成器
    if _excuse_generator is None:
        csv_path = f"{DIR_RESOURCE}/excuse_dictionary.csv"
        _excuse_generator = ExcuseGenerator(csv_path=csv_path)

    # 生成借口并返回文本部分
    _, excuse_text = _excuse_generator.generate()
    return excuse_text


if __name__ == "__main__":
    g = ExcuseGenerator(csv_path="config/excuse_dictionary.csv")
    # print(g.excuse_dict)
    num_samples = 20
    special_counter = 0
    pos_counter = 0
    neg_counter = 0
    for s in range(num_samples):
        cat, sample = g.generate()
        if cat == 'special':
            special_counter += 1
            cat = f'{cat} '  # print output alignment
        elif cat == 'positive':
            pos_counter += 1
        elif cat == 'negative':
            neg_counter += 1
        print(cat, sample)
    print(
        f'special counter: {(special_counter / num_samples):.2f}, theoritical: {(1 - g.person_prob - g.object_prob):.2f}')
    print(
        f'positive counter: {(pos_counter / num_samples):.2f}, theoritical: {(g.person_prob * g.positive_prob):.2f}+{(g.object_prob * g.positive_prob):.2f}={(g.person_prob * g.positive_prob + g.object_prob * g.positive_prob):.2f}')
    print(
        f'negative counter: {(neg_counter / num_samples):.2f}, theoritical: {(g.person_prob * (1 - g.positive_prob)):.2f}+{(g.object_prob * (1 - g.positive_prob)):.2f}={(g.person_prob * (1 - g.positive_prob) + g.object_prob * (1 - g.positive_prob)):.2f}')
