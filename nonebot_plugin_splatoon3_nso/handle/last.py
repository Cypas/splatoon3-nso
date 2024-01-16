import json
import time
from datetime import datetime as dt, timedelta

from .battle import get_battle_msg_md
from .coop import get_coop_msg_md
from .send_msg import bot_send
from .utils import _check_session_handler, get_game_sp_id_and_name, get_battle_time_or_coop_time
from ..data.data_source import dict_get_or_set_user_info, model_get_or_set_user
from ..s3s.splatnet_image import get_app_screenshot, init_browser
from ..s3s.splatoon import Splatoon
from ..s3s.utils import SPLATNET3_URL
from ..utils.bot import *

last = on_command("last", priority=10, block=True)


@last.handle(parameterless=[Depends(_check_session_handler)])
async def _(bot: Bot, event: Event):
    """获取上一局对战或打工数据图"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()

    get_battle = False
    get_coop = False
    get_pic = False
    get_ss = False
    mask = False
    idx = 0
    cmd_message = event.get_plaintext()[5:].strip()
    logger.debug(f'last: {cmd_message}')
    # 筛选参数
    if cmd_message:
        cmd_lst = cmd_message.split(" ")
        if 'b' in cmd_lst or 'battle' in cmd_lst:
            get_battle = True
        if 'c' in cmd_lst or 'coop' in cmd_lst:
            get_coop = True
        if 'p' in cmd_lst or 'pic' in cmd_lst:
            get_pic = True
        if 'ss' in cmd_lst or 'screenshot' in cmd_lst:
            get_ss = True
        if 'm' in cmd_lst or 'mask' in cmd_lst:
            mask = True
        for cmd in cmd_lst:
            if cmd.isdigit():
                # 数字索引
                idx = min(49, max(0, int(cmd) - 1))
                break

    image_width = 720
    if get_pic:
        image_width = 1000
    msg, is_playing = await get_last_battle_or_coop(platform, user_id, get_battle=get_battle,
                                                    get_coop=get_coop,
                                                    get_pic=get_pic,
                                                    idx=idx,
                                                    get_screenshot=get_ss, mask=mask)
    photo = None
    if get_ss:
        photo = msg
        msg = ''
    await bot_send(bot, event, msg, photo=photo, image_width=image_width)

    user = dict_get_or_set_user_info(platform, user_id)
    if user.push_cnt < 3 and (not isinstance(bot, QQ_Bot)):
        logger.info(f'is_playing: {is_playing}')
        if is_playing:
            msg = ''
            if 'group' in event.get_event_name():
                if not user.push_cnt:
                    msg = '正在游玩时可以 /push 开启推送模式~'
            else:
                if user.push_cnt < 3:
                    msg = '正在游玩时可以 /push 开启推送模式~'
            if msg:
                await bot_send(bot, event, msg)


async def get_last_battle_or_coop(platform, user_id, for_push=False, get_battle=False, get_coop=False, get_pic=False,
                                  idx=0, get_screenshot=False, mask=False):
    """获取最近全部对战或打工数据"""
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(platform, user.user_id, user.user_name, user.session_token, user.req_client)
    battle_t = ""
    coop_t = ""

    # res = await splatoon.get_test()
    # res = await splatoon.get_battle_detail("VnNIaXN0b3J5RGV0YWlsLXUtYTQ3ajZtbm1jbWp5eDJoejdsdW06QkFOS0FSQToyMDI0MDExMlQwMjAyNDZfN2M5N2IyNWEtYWMzMi00OWQ5LWEyODAtYTE0YzllOTVmMTQ5")
    # res = await splatoon.get_x_battles()
    # data = translate_rid.get("BankaraBattleHistoriesQuery")
    # res = await splatoon._request(data)

    # print(json.dumps(res))

    # t = time.time()
    #
    # # pic = await get_app_screenshot(user, url=url, mask=mask)
    # res = await splatoon.get_x_battles()
    #
    # tt_date = time.time()
    # tt = f'{tt_date - t:.3f}'
    #
    # # pic = await get_app_screenshot(user, url=url, mask=mask)
    # res = await splatoon.get_last_one_battle()
    #
    # tt2_date = time.time()
    # tt2 = f'{tt2_date - tt_date:.3f}'
    #
    # # pic = await get_app_screenshot(user, url=url, mask=mask)
    # res = await splatoon.get_recent_battles()
    #
    # tt3_date = time.time()
    # tt3 = f'{tt3_date - tt2_date:.3f}'


    if get_coop:
        get_battle = False

    if not get_coop:
        # idx为0情况下直接获取最新对战id
        if idx == 0:
            # 获取最新一场对战的id
            res = await splatoon.get_last_one_battle()
            if not res:
                # 再次尝试一次
                res = await splatoon.get_last_one_battle()
                if not res:
                    return f'`网络错误，请稍后再试.`', False
            b_info = res['data']['vsResult']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]
            # 这个b_info实际上不完整，可用信息只有battle_id和mode，但响应速度整体都低于查询最近对战信息
            battle_id = b_info['id']
            battle_t = get_battle_time_or_coop_time(battle_id)
        else:
            # 获取最近全部对战
            res = await splatoon.get_recent_battles()
            if not res:
                # 再次尝试一次
                res = await splatoon.get_recent_battles()
                if not res:
                    return f'`网络错误，请稍后再试.`', False

            b_info = res['data']['latestBattleHistories']['historyGroups']['nodes'][0]['historyDetails']['nodes'][idx]
            battle_id = b_info['id']
            battle_t = get_battle_time_or_coop_time(battle_id)

    if not get_battle:
        # 获取最近全部打工
        res = await splatoon.get_coops()
        try:
            coop = res['data']['coopResult']
            # /last c 2 指令可能存在跨期查询的问题，idx需要查询每期nodes数量
            coop_group_idx = 0
            # 计算过去有记录的全部打工数据
            coop_total_count = 0
            # 加回1 方便语义计算
            idx += 1
            for group in coop['historyGroups']['nodes']:
                group_count = len(group['historyDetails']['nodes'])
                coop_total_count += group_count
                if idx > group_count:
                    # 超出一组记录
                    idx -= group_count
                    coop_group_idx += 1
            if idx > coop_total_count:
                msg = "查询索引超出最大历史记录，请用更小索引重试"
                is_playing = False
                return msg, is_playing
            # 减1变回索引
            idx -= 1
            coop_info = {
                'coop_point': coop['pointCard']['regularPoint'] or "0",
                'coop_highest_eggs': coop['historyGroups']['nodes'][coop_group_idx]['highestResult'].get(
                    'jobScore') or "0"
            }  # coop_eggs为当期获得的最多的蛋数
            coop_id = coop['historyGroups']['nodes'][coop_group_idx]['historyDetails']['nodes'][idx]['id']
            coop_t = get_battle_time_or_coop_time(coop_id)
        except Exception as e:
            coop_info = {}
            coop_id = ""

    # 未指定模式下
    if (not get_coop) and (not get_battle):
        if battle_t > coop_t:
            get_battle = True
        else:
            get_battle = False

    # 计算是否正在游玩
    str_time = max(battle_t, coop_t)
    str_time = str_time.replace('T', ' ').replace('Z', '')
    dt_time = dt.strptime(str_time, '%Y%m%d %H%M%S')
    if dt.utcnow() - dt_time <= timedelta(hours=1):
        is_playing = True
    else:
        is_playing = False

    if get_battle:
        # 获取对战数据
        if for_push:
            return battle_id, b_info, True
        if get_screenshot:
            try:
                url = f"{SPLATNET3_URL}/history/detail/{battle_id}?lang=zh-CN"
                pic = await get_app_screenshot(user, url=url, mask=mask)
            except Exception as e:
                logger.exception(e)
                pic = None
            return pic, is_playing

        try:
            user_info = json.loads(user.user_info)
        except:
            user_info = {}
        msg = await get_last_msg(splatoon, battle_id, b_info, is_battle=True, get_pic=get_pic, mask=mask)
        return msg, is_playing
    else:
        # 获取打工数据
        if for_push:
            return coop_id, coop_info, False
        if get_screenshot:
            try:
                url = f"{SPLATNET3_URL}/coop/{coop_id}?lang=zh-CN"
                pic = await get_app_screenshot(user, url=url, mask=mask)
            except Exception as e:
                logger.exception(e)
                pic = None
            return pic, is_playing

        msg = await get_last_msg(splatoon, coop_id, coop_info, is_battle=False, get_pic=get_pic, mask=mask)
        return msg, is_playing


async def get_last_msg(splatoon, _id, extra_info, is_battle=True, get_pic=False, mask=False):
    # 获取最后对战或打工的md文本
    try:
        if is_battle:
            battle_detail = await splatoon.get_battle_detail(_id)
            # 取game_sp_id
            if not splatoon.user_db_info.game_sp_id:
                my_team = battle_detail['data']['vsHistoryDetail']['myTeam']
                p = {}
                for _p in my_team['players']:
                    if _p.get('isMyself'):
                        p = _p
                        break
                game_sp_id, game_name = get_game_sp_id_and_name(p)
                splatoon.set_user_info(game_sp_id=game_sp_id, game_name=game_name)

            msg = await get_battle_msg_md(extra_info, battle_detail, splatoon=splatoon, get_pic=get_pic, mask=mask)
        else:
            coop_detail = await splatoon.get_coop_detail(_id)
            msg = await get_coop_msg_md(extra_info, coop_detail, mask=mask)

    except Exception as e:
        logger.exception(e)
        msg = f'get last {"battle" if is_battle else "coop"} failed, please try again later.'
    return msg
