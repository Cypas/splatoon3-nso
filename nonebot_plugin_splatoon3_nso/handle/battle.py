from datetime import datetime as dt, timedelta

from .battle_tools import get_b_point_and_process, set_statics, get_x_power_and_process, get_top_user, get_top_all_name, \
    PushStatistics
from .utils import get_user_name_color, get_game_sp_id_and_name, dict_b_mode_trans
from ..data.data_source import global_user_info_dict, model_get_temp_image_path, model_get_user_friend
from ..data.db_sqlite import UserFriendTable

from ..utils.bot import *


async def get_battle_msg_md(b_info, battle_detail, get_equip=False, idx=0, splatoon=None, mask=False,
                            push_st: PushStatistics = None):
    """获取对战信息md"""

    battle_detail = battle_detail['data']['vsHistoryDetail'] or {}
    # 游戏模式
    mode = battle_detail['vsMode']['mode']
    # 胜负
    judgement = battle_detail['judgement']
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
|---|---|---|---|---|---|
|武器|帽子|上衣|鞋子|背景|徽章|
'''
    else:
        # 战绩
        body = """||||||||||
|---|---:|----:|----:|---:|---:|:---:|---:|:----|
|武器|总|杀+助|死亡|kd<td colspan="2">大招</td> |涂地|玩家|
"""

    text_list = []
    teams = [battle_detail['myTeam']] + battle_detail['otherTeams']
    for team in sorted(teams, key=lambda x: x['order']):
        team_power = []
        for p in team['players']:
            is_last_p = True if p == team['players'][-1] else False
            if get_equip:
                text_list.append(await get_row_user_equip(p))
            else:
                text_list.append(await get_row_user_stats(p, mask, is_last_p, team_power))

        ti = '||'
        if mode == 'FEST':
            _str_team = f"{(team.get('result') or {}).get('paintRatio') or 0:.2%}  {team.get('festTeamName')}"
            _c = team.get('color') or {}
            if _c and 'r' in _c:
                _str_color = f"rgba({int(_c['r'] * 255)}, {int(_c['g'] * 255)}, {int(_c['b'] * 255)}, {_c['a']})"
                _str_team = f"<span style='color:{_str_color}'>{_str_team}</span>"
            ti = f"|||||||||{_str_team}|"
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
    score = ' : '.join(score_list)
    str_open_power = ''
    str_max_open_power = ''
    last_power = ''
    if (not mask and
            ((battle_detail.get('bankaraMatch') or {}).get('mode') == 'OPEN' or
             battle_detail.get('leagueMatch') or
             mode == 'FEST')):
        open_power = ((battle_detail.get('bankaraMatch') or {}).get('bankaraPower') or {}).get('power') or 0
        if battle_detail.get('leagueMatch'):
            open_power = battle_detail['leagueMatch'].get('myLeaguePower') or 0
        if mode == 'FEST':
            open_power = (battle_detail.get('festMatch') or {}).get('myFestPower') or 0

        if open_power:
            str_open_power = f'战力: {open_power:.2f}'
            # push_st = {}
            max_open_power = 0
            # 统计
            if push_st:
                max_open_power = push_st.battle.max_open_power
            max_open_power = max(max_open_power, open_power)
            last_power = push_st.battle.open_power
            get_prev = None
            if not last_power:
                get_prev = True
                prev_id = (battle_detail.get('previousHistoryDetail') or {}).get('id')
                if splatoon:
                    # 查询上一局数据
                    prev_info = await splatoon.get_battle_detail(prev_id)
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
                if diff:
                    str_open_power = f"战力: ({diff:+.2f}) {open_power:.2f}"
            if max_open_power and not get_prev:
                str_max_open_power = f', MAX: {max_open_power:.2f}'
            push_st.battle.open_power = open_power
            push_st.battle.max_open_power = max_open_power

        # 开放重新定分置零
        if (not open_power) and (judgement in ('WIN', 'LOST')) and (bool(push_st.battle.max_open_power)):
            push_st.battle.open_power = 0
            push_st.battle.max_open_power = 0

    title += "##### "
    str_open_power_inline = ''
    if str_open_power and (push_st or last_power):
        title += f"{str_open_power}{str_max_open_power} "
    elif str_open_power:
        str_open_power_inline = str_open_power

    try:
        date_play = dt.strptime(battle_detail['playedTime'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=8)
        str_time = (date_play + timedelta(seconds=duration)).strftime('%y-%m-%d %H:%M:%S')
    except Exception as e:
        str_time = ''
    footer = f"\n#### 耗时: {duration}s, {str_time}"
    title += f"{sub_title}   比分:{score}  {b_process} {str_open_power_inline} \n"

    dict_a = {'GOLD': '🏅️', 'SILVER': '🥈', 'BRONZE': '🥉'}
    award_list = [f"{dict_a.get(a['rank'], '')}{a['name']}" for a in battle_detail['awards']]
    footer += ('\n ' + ' '.join(award_list) + '\n')

    # # b_info唯二有用的地方，显示祭典当前等级，但全是日文
    # if mode == 'FEST':
    #     msg += f'\n#### {b_info["player"]["festGrade"]}'

    # push mode
    if push_st:
        # 统计push数据
        push_st.set_battle_st(battle_detail, point)

        # 为查询数据添加部分push统计内容
        b = push_st.battle
        total = b.total
        win = b.win
        lose = b.lose
        if total:
            str_static = f'push期间:{win}胜-{lose}负'
            k = b.k
            a = b.a
            d = b.d
            if k or a or d:
                str_static += f' {k}+{a}k/{d}d'

            succ = b.successive
            if abs(succ) >= 3:
                if succ > 0:
                    str_static += f', {succ}连胜'
                else:
                    str_static += f', {abs(succ)}连败'

            # 2-1 9+2k/8d, 3连胜
            title += f'\n##### {str_static}'

    msg = f"{title}{body}{footer}"

    return msg


async def get_row_user_equip(p):
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


async def get_row_user_stats(p, mask=False, is_last_player=False, team_power=None):
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
    if d == 0:
        d = 1
    if k != 0 and d != 0:
        ration = k / d
    else:
        ration = 0

    sp_name = p["weapon"]["specialWeapon"]["name"] or ""
    sp_img = p["weapon"]["specialWeapon"]["image"]["url"] or ""
    weapon_sp_img = await model_get_temp_image_path("battle_weapon_special", sp_name, sp_img)
    sp_img = f'<img height="25" src="{weapon_sp_img}"/>'

    name = p['name'].replace('`', '&#96;').replace('|', '&#124;')
    if p.get('isMyself'):
        name = f'<b>{name}</b>'
    elif mask:
        name = f'~~我是马赛克~~'

    player_code, player_name = get_game_sp_id_and_name(p)
    if not p.get('isMyself'):
        name = await get_user_name_color(name, player_code)

    # X 五百强分数
    top_str, power = await get_top_user(player_code)
    if top_str:
        name = name.strip() + top_str

    # 其他排行榜分数
    elif not p.get('isMyself'):
        name, power = await get_top_all_name(name, player_code)

    if power and isinstance(team_power, list):
        team_power.append(power)

    if is_last_player and team_power:
        _power = f'{sum(team_power) / len(team_power):.1f}'
        name += f'<span style="position:absolute;margin-top:28px;color:#1e96d2;right:40px">队伍排行榜均分:{_power}</span>'

    weapon_img = ((p.get('weapon') or {}).get('image') or {}).get('url') or ''
    img_type = "battle_weapon_main"
    weapon_main_img = await model_get_temp_image_path(img_type, p['weapon']['name'], weapon_img)
    w_str = f'<img height="40" src="{weapon_main_img}"/>'
    name = f'{name}|'
    t = f"|{w_str}|{ak:>2}|{k_str:>5}k | {d:>2}d|{ration:>4.1f}|{sp}|{sp_img}| {p['paint']:>4}p| {name}|\n"
    return t


async def get_battle_msg_title(b_info, battle_detail, splatoon=None, mask=False, idx=0):
    """获取对战标题 点数 挑战进度"""

    mode = battle_detail['vsMode']['mode']
    rule = battle_detail['vsRule']['name']
    judgement = battle_detail['judgement']
    stage = battle_detail['vsStage']['name']
    bankara_match = (battle_detail.get('bankaraMatch') or {}).get('mode') or ''

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
            str_point = f'点数{point}p'
        elif battle_detail.get('xMatch'):
            str_point = f'x分变更:{point}'
            point = 0

    # 祭典
    if mode == 'FEST':

        mode_id = battle_detail['vsMode']['id']
        bankara_match = 'CHALLENGE'
        if mode_id == 'VnNNb2RlLTY=':
            bankara_match = 'OPEN'
        elif mode_id == 'VnNNb2RlLTg=':
            bankara_match = 'TRI_COLOR'
        fest_match = battle_detail.get('festMatch') or {}
        contribution = fest_match.get('contribution')
        if contribution:
            str_point = f'+{contribution}'
        if fest_match.get('dragonMatchType') == 'DECUPLE':
            rule += ' (x10)'
        elif fest_match.get('dragonMatchType') == 'DRAGON':
            rule += ' (x100)'
        elif fest_match.get('dragonMatchType') == 'DOUBLE_DRAGON':
            rule += ' (x333)'

    elif mode == 'LEAGUE':
        bankara_match = ((battle_detail.get('leagueMatch') or {}).get('leagueMatchEvent') or {}).get('name')

    # 取翻译名
    mode = dict_b_mode_trans.get(mode, mode)
    if bankara_match:
        bankara_match = dict_b_mode_trans.get(bankara_match, bankara_match)
        bankara_match = f'({bankara_match})'

    if mask:
        # 打码
        str_point = ''

    # b_info唯一有用的地方的就只是这里了，对战详查里面确实没有提供段位
    level = b_info.get('udemae', "")
    if level:
        level_str = level
    else:
        level_str = ""
    # BANKARA(OPEN) 真格蛤蜊 WIN S+9 +8p
    # FEST(OPEN) 占地对战 WIN  +2051
    title = f"{mode}{bankara_match} {rule}({stage}) {judgement}"
    sub_title = f"{level_str} {str_point}"
    return title, sub_title, point, b_process
