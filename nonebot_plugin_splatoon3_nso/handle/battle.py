from datetime import datetime as dt, timedelta

from .b_or_c_tools import get_b_point_and_process, get_x_power_and_process, get_x_username, get_top_all_username, \
    PushStatistics, get_user_name_color, get_badge_username
from .utils import get_game_sp_id_and_name, dict_b_mode_trans, get_icon_path, get_badges_point
from ..data.data_source import model_get_temp_image_path, model_get_user_friend
from ..data.db_sqlite import UserFriendTable
from ..s3s.splatoon import Splatoon
from ..utils import get_time_now_china_date, plugin_release_time, get_time_now_china

DICT_HTML_CODES = {
    '#': '&#35;',
    '`': '&#96;',
    '|': '&#124;',
    '*': '&#42;',
    '_': '&#95;',
    '<': '&#60;',
    '>': '&#62;',
    '~': '&#126;',
}


async def get_battle_msg_md(b_info, battle_detail, get_equip=False, idx=0, splatoon: Splatoon = None, mask=False,
                            push_statistics: PushStatistics = None):
    """获取对战信息md"""

    battle_detail = battle_detail['data']['vsHistoryDetail'] or {}
    # 游戏模式
    mode = battle_detail['vsMode']['mode']
    # 胜负
    judgement: str = battle_detail['judgement']
    # 标题 点数 进度(0-3)
    title, sub_title, point, b_process = await get_battle_msg_title(b_info, battle_detail, splatoon=splatoon,
                                                                    mask=False, idx=idx)
    if b_process:
        b_process = f"进度:{b_process}"

    # title
    title = '#### ' + title + '\n\n'

    # body
    if get_equip:
        # 衣服搭配
        body = '''|||||||
|:----|:----|:----|:----|:----|:----|
|武器|帽子|上衣|鞋子|背景|徽章|
'''
    else:
        # 战绩
        body = """||||||||||||
|-|---|---:|----:|----:|---:|---:|:---|---:|:--------|--|
|序|武器|总|杀+助|亡|kd||大|涂地|玩家||
"""

    text_list = []
    teams = [battle_detail['myTeam']]
    teams.extend(battle_detail['otherTeams'])
    # 按内容里的order字段重新排序
    for k1, team in enumerate(sorted(teams, key=lambda x: x['order'])):
        team_power = []
        for k, p in enumerate(team['players']):
            is_last_p = True if p == team['players'][-1] else False
            if get_equip:
                text_list.append(await get_row_user_equip(k1 * 4 + k, p))
            else:
                text_list.append(await get_row_user_stats(k1 * 4 + k, p, mask, is_last_p, team_power, splatoon.nsa_id))

        ti = "||"
        if mode == "FEST":
            _str_team = f"{(team.get('result') or {}).get('paintRatio') or 0:.2%}  {team.get('festTeamName')}"
            _c = team.get('color') or {}
            if _c and "r" in _c:
                _str_color = f"rgba({int(_c['r'] * 255)}, {int(_c['g'] * 255)}, {int(_c['b'] * 255)}, {_c['a']})"
                _str_team = f"<span style='color:{_str_color}'>{_str_team}</span>"
            # 祭典队伍名
            ti = f'|||||||||&nbsp;|' \
                 f'<span style="position:absolute;left:50%;margin-top:-13px">' \
                 f'{_str_team}</span>||'

        text_list.append(f'{ti}\n')
    body += ''.join(text_list)

    # footer
    duration = battle_detail['duration']
    score_list = []
    for t in teams:
        if (t.get('result') or {}).get('score') is not None:
            score_list.append(str((t['result']['score'])))
        elif (t.get('result') or {}).get('paintRatio') is not None:
            score_list.append(f"{t['result']['paintRatio']:.2%}"[:-2])
    score = " : ".join(score_list)
    str_open_power = ""
    str_max_open_power = ""
    last_power = ""
    if (not mask and
            ((battle_detail.get('bankaraMatch') or {}).get('mode') == 'OPEN' or
             battle_detail.get('leagueMatch') or
             mode == "FEST")):
        open_power = ((battle_detail.get('bankaraMatch') or {}).get('bankaraPower') or {}).get('power') or 0
        if battle_detail.get('leagueMatch'):
            open_power = battle_detail['leagueMatch'].get('myLeaguePower') or 0
        if mode == "FEST":
            open_power = (battle_detail.get('festMatch') or {}).get('myFestPower') or 0

        if open_power:
            # 蛮颓开放
            str_open_power = f"战力: {open_power:.2f}"
            # push_st = {}
            max_open_power = 0

            last_power = None
            if push_statistics:
                # 统计置分
                max_open_power = push_statistics.battle.max_open_power
                max_open_power = max(max_open_power, open_power)
                last_power = push_statistics.battle.open_power
            get_prev = False
            # 获取过去一局数据
            if not last_power:
                get_prev = True
                prev_id = (battle_detail.get('previousHistoryDetail') or {}).get('id')
                if splatoon:
                    # 查询上一局数据
                    prev_info = await splatoon.get_battle_detail(prev_id, multiple=True)
                    if prev_info:
                        prev_detail = prev_info.get('data', {}).get('vsHistoryDetail') or {}
                        prev_open_power = ((prev_detail.get('bankaraMatch') or {}).get('bankaraPower') or {}).get(
                            'power') or 0
                        if prev_detail and not prev_open_power:
                            prev_open_power = (prev_detail.get('leagueMatch') or {}).get('myLeaguePower') or 0
                        if mode == 'FEST' and prev_detail and not prev_open_power:
                            prev_open_power = (prev_detail.get('festMatch') or {}).get('myFestPower') or 0
                        if prev_open_power:
                            last_power = prev_open_power

            if last_power:
                diff = open_power - last_power
                str_open_power = f"分数: ({diff:+.2f}) {open_power:.2f}"
            if push_statistics:
                if max_open_power and not get_prev:
                    str_max_open_power = f', 最高分数: {max_open_power:.2f}'
                push_statistics.battle.open_power = open_power
                push_statistics.battle.max_open_power = max_open_power

                # 开放重新定分置零
                if (not open_power) and (judgement != "DRAW") and push_statistics.battle.max_open_power:
                    push_statistics.battle.open_power = 0
                    push_statistics.battle.max_open_power = 0

    title += "##### "
    str_open_power_inline = ''
    if str_open_power and (push_statistics or last_power):
        title += f"{str_open_power}{str_max_open_power} "
    elif str_open_power:
        str_open_power_inline = str_open_power

    try:
        date_play = dt.strptime(battle_detail['playedTime'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=8)
        str_time = date_play.strftime('%y-%m-%d %H:%M:%S')
    except Exception as e:
        str_time = ""
    footer = f"\n#### 时间: {str_time}  耗时: {duration}s"
    title += f"{sub_title}   比分:{score}  {b_process} {str_open_power_inline} \n"

    dict_a = {'GOLD': '🏅️', 'SILVER': '🥈', 'BRONZE': '🥉'}
    award_list = [f"{dict_a.get(a['rank'], '')}{a['name']}" for a in battle_detail['awards']]
    title += ('##### 奖牌:' + ' '.join(award_list) + '\n')

    # 打印图例说明
    user_create_dt = splatoon.user_db_info.create_time + timedelta(days=7)
    plugin_release_dt = get_time_now_china_date(plugin_release_time) + timedelta(days=7)
    now_dt = get_time_now_china()
    if (now_dt < plugin_release_dt or now_dt < user_create_dt) and not push_statistics:
        footer += f'\n###### 本注解说明会在登录7天后不再显示' \
                  f'</br>用户名颜色: <b>粗体黑色</b>:玩家自己，' \
                  f'<span style="color:green">绿色 </span> :已在bot登录的用户，' \
                  f'<span style="color:skyblue">浅蓝色 </span> :某个已登录用户的好友(大概率国人)' \
                  f'</br>用户名下面分数: ' \
                  f'<span style="color:#EE9D59">E(2400) </span> : 活动比赛上榜最高分，' \
                  f'<span style="color:#EE9D59">F(2400) </span> :祭典百杰最高分' \
                  f'</br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&nbsp;' \
                  f'<span style="color:red">X12(3000) </span> :日服五百强排名及分数，' \
                  f'<span style="color:#fc0390">X12(3000) </span> :美服五百强排名及分数' \
                  f'</br>&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&nbsp;' \
                  f'<span style="color:red">BX50000(2144.4↑) </span> :日服根据其展示徽章对X赛排名，分数的估算，' \
                  f'<span style="color:#fc0390">BX50000(2014↑) </span> :美服徽章估分' \
                  f'</br>用户名右侧头像或武器: 一般都为<span style="color:skyblue">浅蓝色</span>用户的头像,如果是武器，则是以上榜单用户上榜时所用的武器'

        # # b_info唯二有用的地方，显示祭典当前等级，但全是日文
    # if mode == 'FEST':
    #     msg += f'\n#### {b_info["player"]["festGrade"]}'

    # push mode
    if push_statistics:
        # 统计push数据
        push_statistics.set_battle_st(battle_detail, point)

        # 为查询数据添加部分push统计内容
        b = push_statistics.battle
        total = b.total
        win = b.win
        lose = b.lose
        if total:
            str_static = f'push期间:{win}胜-{lose}负'
            k = b.k
            a = b.a
            d = b.d
            if k or a or d:
                str_static += f" {k}+{a}k/{d}d"

            succ = b.successive
            if abs(succ) >= 3:
                if succ > 0:
                    str_static += f", {succ}连胜"
                else:
                    str_static += f", {abs(succ)}连败"

            # 2-1 9+2k/8d, 3连胜
            title += f'\n##### {str_static}'

    title += "\n"
    msg = f"{title}{body}{footer}"
    return msg


async def get_row_user_equip(k_idx, p):
    """获取一行对战玩家装备信息
    p:player的一个遍历对象
    """
    a, b, c = 43, 30, 20

    # 上衣
    img_type = "battle_headGear"
    img1 = await model_get_temp_image_path(img_type, p['headGear']['name'], p['headGear']['originalImage']['url'])
    head_gear = f"<img height='{a}' src='{img1}'/>"

    img_type = "battle_primaryGearPower"
    img2 = await model_get_temp_image_path(img_type, p['headGear']['primaryGearPower']['name'],
                                           p['headGear']['primaryGearPower']['image']['url'])
    head_gear += f"<img height='{b}' src='{img2}'/>"

    for g in p['headGear']['additionalGearPowers']:
        img_type = "battle_additionalGearPowers"
        img3 = await model_get_temp_image_path(img_type, g['name'], g['image']['url'])
        head_gear += f"<img height='{c}' src='{img3}'/>"

    # 服装
    img_type = "battle_clothingGear"
    img1 = await model_get_temp_image_path(img_type, p['clothingGear']['name'],
                                           p['clothingGear']['originalImage']['url'])
    clothing_gear = f"<img height='{a}' src='{img1}'/>"

    img_type = "battle_primaryGearPower"
    img2 = await model_get_temp_image_path(img_type, p['clothingGear']['primaryGearPower']['name'],
                                           p['clothingGear']['primaryGearPower']['image']['url'])
    clothing_gear += f"<img height='{b}' src='{img2}'/>"

    for g in p['clothingGear']['additionalGearPowers']:
        img_type = "battle_additionalGearPowers"
        img3 = await model_get_temp_image_path(img_type, g['name'], g['image']['url'])
        clothing_gear += f"<img height='{c}' src='{img3}'/>"

    # 鞋子
    img_type = "battle_shoesGear"
    img1 = await model_get_temp_image_path(img_type, p['shoesGear']['name'], p['shoesGear']['originalImage']['url'])
    shoes_gear = f"<img height='{a}' src='{img1}'/>"

    img_type = "battle_primaryGearPower"
    img2 = await model_get_temp_image_path(img_type, p['shoesGear']['primaryGearPower']['name'],
                                           p['shoesGear']['primaryGearPower']['image']['url'])
    shoes_gear += f"<img height='{b}' src='{img2}'/>"

    for g in p['shoesGear']['additionalGearPowers']:
        img_type = "battle_additionalGearPowers"
        img3 = await model_get_temp_image_path(img_type, g['name'], g['image']['url'])
        shoes_gear += f"<img height='{c}' src='{img3}'/>"

    # 武器
    weapon_img = ((p.get('weapon') or {}).get('image2d') or {}).get('url') or ''
    weapon_name = ((p.get('weapon') or {}).get('name') or '')
    img_type = "battle_weapon_main"
    img1 = await model_get_temp_image_path(img_type, weapon_name, weapon_img)
    weapon = f"<img height='{a}' src='{img1}'/>"

    img_type = "battle_weapon_sub"
    img2 = await model_get_temp_image_path(img_type, p['weapon']['subWeapon']['name'],
                                           p['weapon']['subWeapon']['image']['url'])
    weapon += f"<img height='{b}' src='{img2}'/>"

    img_type = "battle_weapon_special"
    img3 = await model_get_temp_image_path(img_type, p['weapon']['specialWeapon']['name'],
                                           p['weapon']['specialWeapon']['image']['url'])
    weapon += f"<img height='{b}' src='{img3}'/>"

    # 获取好友数据库的步骤是通过好友列表实现的，但好友列表只提供了game_name，没有提供name_id，此处搜索只能粗略判断
    user_friend: UserFriendTable = model_get_user_friend(p['name'])
    if user_friend:
        img_type = "friend_icon"
        # 储存名使用friend_id
        img = await model_get_temp_image_path(img_type, user_friend.friend_id, user_friend.user_icon)
        weapon += f"<img height='{a}' style='position:absolute;left:10px' src='{img}'/>"
    # # 用户其他信息无需联动好友数据库，储存名改为 game_name + name_id 唯一标识    暂未使用
    # game_name = f"{p['name']}#{p['nameId']}"

    img_type = "user_nameplate_bg"
    img_bg = await model_get_temp_image_path(img_type, p['nameplate']['background']['id'],
                                             p['nameplate']['background']['image']['url'])
    name = f"{head_gear}|{clothing_gear}|{shoes_gear}|<img height='{a}' src='{img_bg}'/>|"
    for b in (p.get('nameplate') or {}).get('badges') or []:
        if not b:
            continue
        badge_img = (b.get('image') or {}).get('url') or ''
        if badge_img != "":
            img_type = "user_nameplate_badge"
            img_badge = await model_get_temp_image_path(img_type, b['id'], badge_img)
            name += f'<img height="{a}" src="{img_badge}"/>'
    t = f"| {weapon} | {name}|\n"
    return t


async def get_row_user_stats(k_idx, p, mask=False, is_last_player=False, team_power=None, nsa_id=None):
    """获取一行对战玩家战绩
    p:player的一个遍历对象
    """
    re = p['result']
    if not re:
        re = {"kill": 0, "death": 0, "assist": 0, "special": 0}
    ak = re['kill']
    k = re['kill'] - re['assist']
    k_str = f'{k}+{re["assist"]}'
    d = re['death']
    sp = re['special']
    # 避免除数和被除数为0的情况
    if k != 0:
        if d == 0:
            ration = k / 1
        else:
            ration = k / d
    else:
        ration = 0

    sp_name = p["weapon"]["specialWeapon"]["name"] or ""
    sp_img = p["weapon"]["specialWeapon"]["image"]["url"] or ""
    weapon_sp_img = await model_get_temp_image_path("battle_weapon_special", sp_name, sp_img)
    sp_img = f'<img height="25" src="{weapon_sp_img}"/>'

    name = p['name']
    for k, v in DICT_HTML_CODES.items():
        name = name.replace(k, v)

    player_code, player_name = get_game_sp_id_and_name(p)
    icon = ""
    if p.get('isMyself'):
        name, icon = await get_user_name_color(name, player_code, is_myself=True, nsa_id=nsa_id)
    elif mask:
        name = f"~~我是马赛克~~"
    if not p.get('isMyself'):
        name, icon = await get_user_name_color(name, player_code)

    origin_name = name
    # X 五百强分数
    name, icon, power = await get_x_username(origin_name, icon, player_code)
    if (not power) and (not p.get('isMyself')):
        # 其他排行榜分数
        name, icon, power = await get_top_all_username(origin_name, icon, player_code)

    # 通过徽章算分
    badges_list = []
    for b in (p.get('nameplate') or {}).get('badges') or []:
        if not b:
            continue
        badge_name = b.get('id') or ''
        badge_img = (b.get('image') or {}).get('url') or ''
        if badge_img != "":
            img_type = "user_nameplate_badge"
            await model_get_temp_image_path(img_type, b['id'], badge_img)
            badges_list.append(badge_name)
    area, ranking, max_badge, badge_badge_point = get_badges_point(badges_list)
    if badge_badge_point > power:
        # 徽章置分
        name, icon, power = await get_badge_username(origin_name, icon, area, ranking, max_badge, badge_badge_point)

    if power and isinstance(team_power, list):
        team_power.append(power)

    weapon_img = ((p.get('weapon') or {}).get('image') or {}).get('url') or ''
    img_type = "battle_weapon_main"
    weapon_main_img = await model_get_temp_image_path(img_type, p['weapon']['name'], weapon_img)
    w_str = f'<img height="40" src="{weapon_main_img}"/>'

    _i = 97  # 97号为a，为top提供索引 abcdefgh
    t = f"|{chr(_i + k_idx)}|{w_str}|{ak:>2}|{k_str:>5}k | {d:>2}d|{ration:>4.1f}|{sp_img}|{sp}| {p['paint']:>4}p| {name}|{icon}|\n"
    if is_last_player and team_power:
        _power = f'{sum(team_power) / len(team_power):.1f}'
        t += f'|||||||||&nbsp; |' \
             f'<span style="position:absolute;left:50%;margin-top:-13px">' \
             f'队伍成员上榜均分:' \
             f'<span style="color:#1e96d2">{_power}</span></span>|\n'
    return t


async def get_battle_msg_title(b_info, battle_detail, splatoon=None, mask=False, idx=0):
    """获取对战标题 点数 挑战进度"""

    mode = battle_detail['vsMode']['mode']
    rule = battle_detail['vsRule']['name']
    judgement = battle_detail['judgement']
    # 取胜负的翻译
    judgement = (judgement.replace("DEEMED_LOSE", "自己掉线")
                 .replace("EXEMPTED_LOSE", "队友掉线，免除惩罚")
                 .replace("DRAW", "一分钟内有人掉线，无效对局")
                 )
    stage = battle_detail['vsStage']['name']
    bankara_match = (battle_detail.get('bankaraMatch') or {}).get('mode') or ''

    # 取图标
    rule_icon_path = get_icon_path(rule)
    if rule_icon_path != "":
        rule = f'<img height="40" src="{rule_icon_path}"/>'

    point = 0
    b_process = ''
    if bankara_match:
        # 挑战点数，挑战进度
        point, b_process = await get_b_point_and_process(battle_detail, bankara_match=bankara_match, splatoon=splatoon,
                                                         idx=idx)
    elif battle_detail.get('xMatch'):
        point, b_process = await get_x_power_and_process(battle_detail, splatoon, idx=idx)

    str_point = ''
    if point:
        if bankara_match:
            str_point = f"点数{point}p"
        elif battle_detail.get('xMatch'):
            str_point = f"x分变更:{point}"
            point = 0

    # 祭典
    if mode == "FEST":

        mode_id = battle_detail['vsMode']['id']
        bankara_match = "CHALLENGE"
        if mode_id == "VnNNb2RlLTY=":
            bankara_match = "OPEN"
        elif mode_id == "VnNNb2RlLTg=":
            bankara_match = "TRI_COLOR"
        fest_match = battle_detail.get('festMatch') or {}
        contribution = fest_match.get('contribution')
        if contribution:
            str_point = f'+{contribution}'
        if fest_match.get('dragonMatchType') == 'DECUPLE':
            rule += " <span style='color:skyblue'>(x10)</span>"
        elif fest_match.get('dragonMatchType') == 'DRAGON':
            rule += " <span style='color:red'>(x100)</span>"
        elif fest_match.get('dragonMatchType') == 'DOUBLE_DRAGON':
            rule += " <span style='color:red'>(x333)</span>"

    elif mode == "LEAGUE":
        bankara_match = ((battle_detail.get('leagueMatch') or {}).get('leagueMatchEvent') or {}).get('name')

    # 取翻译名
    mode = dict_b_mode_trans.get(mode, mode)
    mode_name = mode
    # 取图标
    mode_icon_path = get_icon_path(mode)
    if mode_icon_path != "":
        mode = f'<img height="40" src="{mode_icon_path}"/>'

    if bankara_match:
        bankara_match = dict_b_mode_trans.get(bankara_match, bankara_match)
        bankara_match = f"({bankara_match})"

    mode_match = f'{mode_name}{bankara_match}'
    mode_match_icon_path = get_icon_path(mode_match)
    if mode_match_icon_path != "" and mode_match != mode_match_icon_path:
        mode_match = f'<img height="40" src="{mode_match_icon_path}"/>{bankara_match}'
    else:
        mode_match = f'{mode}{bankara_match}'

    if mask:
        # 打码
        str_point = ""

    # b_info唯一有用的地方的就只是这里了，对战详查里面确实没有提供段位
    level = b_info.get('udemae', "")
    if level:
        level_str = level
    else:
        level_str = ""
    # BANKARA(OPEN) 真格蛤蜊 WIN S+9 +8p
    # FEST(OPEN) 占地对战 WIN  +2051
    if mode_name != "一般比赛":
        title = f"{mode_match} {rule}({stage}) {judgement}"
    else:
        title = f"{mode_match} ({stage}) {judgement}"

    sub_title = f"{level_str} {str_point}"
    return title, sub_title, point, b_process
