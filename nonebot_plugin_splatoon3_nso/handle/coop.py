from datetime import datetime as dt, timedelta

from .b_or_c_tools import PushStatistics, get_user_name_color
from .utils import get_game_sp_id_and_name, get_icon_path
from ..data.data_source import model_get_temp_image_path
from ..s3s.splatoon import Splatoon
from ..utils import get_time_now_china_date, get_time_now_china, plugin_release_time
from ..utils.bot import *


async def get_coop_msg_md(coop_info, coop_detail, coop_defeat=None, mask=False, splatoon: Splatoon = None, push_statistics: PushStatistics = None):
    """获取打工的md文本"""
    c_point = coop_info.get('coop_point')
    c_eggs = coop_info.get('coop_highest_eggs')
    detail = coop_detail['data']['coopHistoryDetail']
    my = detail['myResult']
    wave_msg = '''| | | |  |
| :--- |:---:|:---:|:---:|
| 波数 | 提交/需求(出现) |潮位|大招|
'''
    d_w = {0: "退潮", 1: "平潮", 2: "涨潮"}
    win = False
    total_deliver_cnt = 0
    wave_cnt = 3
    if detail.get('rule') == 'TEAM_CONTEST':
        wave_cnt = 5
    if detail['resultWave'] == 0:  # 0为胜利(未失败)  -1为掉线
        win = True

    # rule图标
    rule_icon = ""
    rule = detail.get('rule')
    if rule:
        # 取图标
        rule_icon_path = get_icon_path(rule)
        if rule_icon_path != "":
            rule_icon = f'<img height="40" src="{rule_icon_path}"/>'
    # 全部w的数据
    wave_results = detail['waveResults'][:wave_cnt]
    for w in wave_results:
        event = (w.get('eventWave') or {}).get('name') or ''
        specs = ""
        for s in w.get('specialWeapons') or []:
            img_type = "coop_special"
            img = await model_get_temp_image_path(img_type, s['name'], s['image']['url'])
            specs += f'<img height="18" src="{img}"/>'
        wave_msg += f"|W{w['waveNumber']} | {w['teamDeliverCount']}/{w['deliverNorm']}({w['goldenPopCount']}) |" \
                    f"{d_w[w['waterLevel']]} {event}| {specs} |\n"
        total_deliver_cnt += w['teamDeliverCount'] or 0

    if detail.get('bossResult'):
        # EX wave
        w = detail['waveResults'][-1]
        r = "GJ!" if detail['bossResult']['hasDefeatBoss'] else "NG"
        s = ""
        scale = detail.get('scale')
        if scale and scale.get('gold'):
            s += f' 🏅️{scale["gold"]}'
        if scale and scale.get('silver'):
            s += f' 🥈{scale["silver"]}'
        if scale and scale.get('bronze'):
            s += f' 🥉{scale["bronze"]}'
        boss_name = detail['bossResult']['boss']['name']
        defeat = "0"
        if coop_defeat:
            defeat = coop_defeat["defeat_boss"].get(boss_name, "0")
        # golden_pop_count = w['goldenPopCount']
        # 原来辰龙后面括号是显示出现金蛋数量，但显示为总击杀数量会更合理
        wave_msg += f"EX |{boss_name} (总击杀{defeat}) |{r} {s}||"

    # 蛋数统计  本局蛋数(当期最大蛋数)
    if total_deliver_cnt and c_eggs:
        total_deliver_cnt = f'本局蛋数:{total_deliver_cnt} (本期最多蛋数:{c_eggs})'

    # boss槽
    king_smell = detail.get("smellMeter")
    king_str = f'{king_smell}/5' if king_smell is not None else ''
    # 段位
    lv_grade = detail['afterGrade']['name'] if detail.get('afterGrade') else ''
    lv_point = detail['afterGradePoint'] or ''
    # 打工地图
    coop_stage = detail['coopStage']['name']
    # 胜负情况
    result_wave = detail["resultWave"]
    judgement = "🎉Clear!! " if win else f"😭W{result_wave} Failure"
    msg = f"""
#### {rule_icon}{coop_stage} 段位:{lv_grade} {lv_point}  危险度:{detail['dangerRate']:.0%} {judgement}
##### 打工点数+{detail['jobPoint']}({c_point}p) boss槽:{king_str}
{wave_msg}

#### {total_deliver_cnt}
|||||||||||
| --: |--:|--:|--:|--:|:---------|--:|:--|--|--|
| 击杀 |蛋数|死亡|救人|红蛋|玩家|大|招|武器||
{await coop_row_user(my, wave_results, is_myself=True)}
"""
    for p in detail['memberResults']:
        msg += f"""{await coop_row_user(p, wave_results, mask=mask)}\n"""
    msg += '''\n|||||
|:--:|:--:|:--:|:--|
|全队(自己)|出现|总击杀|boss|
'''

    # 遍历本局击杀boss数
    for e in detail['enemyResults']:
        nice = ''
        if e.get('popCount', 0) <= int(str(e.get('teamDefeatCount') or 0)):
            nice = '√'
        boss_cnt = e.get('teamDefeatCount') or 0
        boss_pop = e['popCount'] or ''
        if e.get('defeatCount'):
            boss_cnt = f'{boss_cnt}({e["defeatCount"]})'
        img_type = "coop_boss"
        boss_name = (e.get('enemy') or {}).get('name') or ''
        img_url = e['enemy']['image']['url']
        img = await model_get_temp_image_path(img_type, boss_name, img_url)
        img_str = f"<img height='18' src='{img}'/>"
        boss_name_str = f"{img_str} {boss_name}"
        if nice:
            boss_cnt = f'<span style="color: green">{boss_cnt}</span>'
            boss_pop = f'<span style="color: green">{boss_pop}</span>'
            boss_name_str = f'<span style="color: green">{boss_name_str}</span>'
        defeat = "0"
        if coop_defeat:
            defeat = coop_defeat["defeat_enemy"].get(boss_name, "0")

        msg += f"""|{boss_cnt} |{boss_pop} | {defeat} | {boss_name_str}|\n"""

    # push mode
    if push_statistics:
        # 统计push数据
        push_statistics.set_coop_st(detail)

    try:
        date_play = dt.strptime(detail['playedTime'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=8)
        str_time = date_play.strftime('%y-%m-%d %H:%M:%S')
        msg += f"\n##### 时间: {str_time}"

        # 打印图例说明
        user_create_dt = splatoon.user_db_info.create_time + timedelta(days=7)
        plugin_release_dt = get_time_now_china_date(plugin_release_time) + timedelta(days=7)
        now_dt = get_time_now_china()
        if now_dt < plugin_release_dt or now_dt < user_create_dt:
            msg += f'\n###### 本注解说明会在登录7天后不再显示' \
                      f'</br>用户名颜色: <b>粗体黑色</b>:玩家自己，' \
                      f'<span style="color:green">绿色 </span> :已在bot登录的用户，' \
                      f'<span style="color:skyblue">浅蓝色 </span> :某个已登录用户的好友(大概率国人)'
    except Exception as e:
        pass

    return msg


async def coop_row_user(p, wave_results, mask=False, is_myself=False):
    """打工获取一行用户"""
    try:
        sp_name = p['specialWeapon']['name']
        sp_residue_count = 2
        for w in wave_results:
            # 计算留大
            for s in w.get('specialWeapons'):
                if sp_name == s['name']:
                    sp_residue_count -= 1

        if sp_residue_count != 0:
            sp_residue = f"剩{sp_residue_count}"
        else:
            sp_residue = ""

        img_type = "coop_special"
        special_img = await model_get_temp_image_path(img_type, p['specialWeapon']['name'],
                                                      p['specialWeapon']['image']['url'])
        weapon = f"<img height='20' src='{special_img}'/> |{sp_residue}|"
        for w in p['weapons']:
            img_type = "coop_weapon"
            weapon_img = await model_get_temp_image_path(img_type, w['name'], w['image']['url'])
            weapon += f"<img height='20' src='{weapon_img}'/>"
    except Exception as e:
        logger.warning(f'coop_row error: {e}')
        weapon = 'w||'

    p_name = p['player']['name']
    img_type = "coop_uniform"
    uniform_img = await model_get_temp_image_path(img_type, p["player"]["uniform"]['name'],
                                                  p["player"]["uniform"]["image"]["url"])
    uniform = f'<img height="18" src="{uniform_img}"/>'

    if mask:
        p_name = f'~~我是马赛克~~'

    player_code, player_name = get_game_sp_id_and_name(p['player'])
    if is_myself:
        p_name, icon = await get_user_name_color(p_name, player_code, is_myself=True)
    else:
        p_name, icon = await get_user_name_color(player_name, player_code)
    # 辅助投蛋数
    if p['goldenAssistCount']:
        golden = f"{p['goldenDeliverCount']}({p['goldenAssistCount']})"
    else:
        golden = f"{p['goldenDeliverCount']}"

    t = f"|x{p['defeatEnemyCount']}| {golden} |{p['rescuedCount']}d |" \
        f"{p['rescueCount']}r|{p['deliverCount']} | {uniform} {p_name}|{weapon}|{icon}|"

    return t
