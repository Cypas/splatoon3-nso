import base64
from datetime import datetime as dt, timedelta

from .utils import get_user_name_color, get_game_sp_id_and_name
from ..data.data_source import model_get_temp_image_path
from ..utils.bot import *


async def get_coop_msg_md(coop_info, coop_detail, mask=False):
    """获取打工的md文本"""
    c_point = coop_info.get('coop_point')
    c_eggs = coop_info.get('coop_highest_eggs')
    detail = coop_detail['data']['coopHistoryDetail']
    my = detail['myResult']
    wave_msg = '''| | | |  |
| :--- |:---:|:---:|:---:|
| 波数 | 提交/需求(出现) |潮位|大招|
'''
    d_w = {0: '退潮', 1: '平潮', 2: '涨潮'}
    win = False
    total_deliver_cnt = 0
    wave_cnt = 3
    if detail.get('rule') == 'TEAM_CONTEST':
        wave_cnt = 5
    if detail['resultWave'] == 0:  # 0为胜利(未失败)  -1为掉线
        win = True
    # 全部w的数据
    wave_results = detail['waveResults'][:wave_cnt]
    for w in wave_results:
        event = (w.get('eventWave') or {}).get('name') or ''
        specs = ''
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
        r = 'GJ!' if detail['bossResult']['hasDefeatBoss'] else 'NG'
        s = ''
        scale = detail.get('scale')
        if scale and scale.get('gold'):
            s += f' 🏅️{scale["gold"]}'
        if scale and scale.get('silver'):
            s += f' 🥈{scale["silver"]}'
        if scale and scale.get('bronze'):
            s += f' 🥉{scale["bronze"]}'
        wave_msg += f"EX |{detail['bossResult']['boss']['name']} ({w['goldenPopCount']}) |{r} {s}||\n"

    # 蛋数统计  本局蛋数(当期最大蛋数)
    if total_deliver_cnt and c_eggs:
        total_deliver_cnt = f'本局蛋数:{total_deliver_cnt} (本期最多蛋数:{c_eggs})'

    # boss槽
    king_smell = detail.get("smellMeter")
    king_str = f'{king_smell}/5' if king_smell else ''
    # 段位
    h_grade = detail['afterGrade']['name'] if detail.get('afterGrade') else ''
    h_point = detail['afterGradePoint'] or ''
    # 打工地图
    coop_stage = detail['coopStage']['name']

    msg = f"""
#### 段位:{h_grade} {h_point}  危险度:{detail['dangerRate']:.0%} {'🎉Clear!! ' if win else '😭Failure'}
### {coop_stage}  点数+{detail['jobPoint']}({c_point}p) boss槽:{king_str}
{wave_msg}

#### {total_deliver_cnt}
|  |   ||  ||||||
| --: |--:|--:|--:|--:|:--|--|--|--|
| 击杀 |蛋数|死亡|红蛋|救人|玩家<td colspan="2">大招</td>|武器|
{await coop_row_user(my,wave_results, is_myself=True)}
"""
    for p in detail['memberResults']:
        msg += f"""{await coop_row_user(p,wave_results, mask=mask)}\n"""
    msg += '''\n|        | ||
|:--:|:--:|:--|
|全队(自己)|出现|boss|
'''
    for e in detail['enemyResults']:
        nice = ''
        if e.get('popCount', 0) <= int(str(e.get('teamDefeatCount') or 0)):
            nice = '√'
        boss_cnt = e.get('teamDefeatCount') or 0
        boss_pop = e['popCount'] or ''
        if e.get('defeatCount'):
            boss_cnt = f'{boss_cnt}({e["defeatCount"]})'
        img_type = "coop_boss"
        img_name = (e.get('enemy') or {}).get('name') or ''
        img_url = e['enemy']['image']['url']
        img = await model_get_temp_image_path(img_type, img_name, img_url)
        img_str = f"<img height='18' src='{img}'/>"
        boss_name = f"{img_str} {img_name}"
        if nice:
            boss_cnt = f'<span style="color: green">{boss_cnt}</span>'
            boss_pop = f'<span style="color: green">{boss_pop}</span>'
            boss_name = f'<span style="color: green">{boss_name}</span>'
        msg += f"""|{boss_cnt} |{boss_pop} | {boss_name}|\n"""

    try:
        date_play = dt.strptime(detail['playedTime'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=8)
        str_time = date_play.strftime('%y-%m-%d %H:%M:%S')
        msg += f"\n##### 时间: {str_time}"
    except Exception as e:
        pass

    # logger.info(msg)
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
        weapon = f"<img height='18' src='{special_img}'/> |{sp_residue}|"
        for w in p['weapons']:
            img_type = "coop_weapon"
            weapon_img = await model_get_temp_image_path(img_type, w['name'], w['image']['url'])
            weapon += f"<img height='18' src='{weapon_img}'/>"
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

    if not is_myself:
        player_code, player_name = get_game_sp_id_and_name(p['player'])
        p_name = await get_user_name_color(p_name, player_code)
    else:
        p_name = f'<b>{p_name}</b>'

    t = f"|x{p['defeatEnemyCount']}| {p['goldenDeliverCount']} |{p['rescuedCount']}d |" \
        f"{p['deliverCount']} |{p['rescueCount']}r| {uniform} {p_name}|{weapon}|"

    return t



