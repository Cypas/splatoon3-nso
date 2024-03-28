from datetime import datetime as dt, timedelta

from .battle import get_battle_msg_md
from .coop import get_coop_msg_md
from .send_msg import bot_send, bot_send_last_md
from .utils import _check_session_handler, get_game_sp_id_and_name, get_battle_time_or_coop_time, get_event_info
from .. import plugin_config
from ..data.data_source import dict_get_or_set_user_info
from ..s3s.splatnet_image import get_app_screenshot
from ..s3s.splatoon import Splatoon
from ..s3s.utils import SPLATNET3_URL
from ..utils.bot import *

matcher_last = on_command("last", priority=10, block=True)


@matcher_last.handle(parameterless=[Depends(_check_session_handler)])
async def last(bot: Bot, event: Event, args: Message = CommandArg()):
    """获取上一局对战或打工数据图"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()

    get_battle = False
    get_coop = False
    get_equip = False
    get_screenshot = False
    get_image = False
    mask = False
    idx = 0
    cmd_message = args.extract_plain_text().strip()
    logger.debug(f'last: {cmd_message}')
    # 筛选参数
    if cmd_message:
        cmd_lst = cmd_message.split(" ")
        if 'b' in cmd_lst or 'battle' in cmd_lst:
            get_battle = True
        if 'c' in cmd_lst or 'coop' in cmd_lst:
            get_coop = True
        if get_battle and get_coop:
            get_battle = False
            get_coop = False
        if 'e' in cmd_lst or 'equip' in cmd_lst:
            get_equip = True
        if 'i' in cmd_lst or 'image' in cmd_lst:
            get_image = True
        if 'ss' in cmd_lst or 'screenshot' in cmd_lst:
            get_screenshot = True
        if 'm' in cmd_lst or 'mask' in cmd_lst:
            mask = True
        for cmd in cmd_lst:
            if cmd.isdigit():
                # 数字索引
                idx = min(49, max(0, int(cmd) - 1))
                break

    image_width = 760
    if get_equip:
        # 查询装备
        get_battle = True
        get_coop = False
        image_width = 1000
        await bot_send(bot, event, "查询装备数据会花费更长一些时间，请稍等")

    if get_screenshot:
        # nso截图
        await bot_send(bot, event, "正在截图nso页面，请稍等")

    msg, is_playing = await get_last_battle_or_coop(bot, event, get_battle=get_battle,
                                                    get_coop=get_coop,
                                                    get_equip=get_equip,
                                                    idx=idx,
                                                    get_screenshot=get_screenshot, mask=mask)

    if isinstance(event, QQ_GME) and plugin_config.splatoon3_qq_md_mode and not get_image:
        # 这里存在 /last ss 的情况，msg值实际为bytes
        await bot_send_last_md(bot, event, msg, user_id, image_width=image_width)
    else:
        await bot_send(bot, event, msg, image_width=image_width)

    if not isinstance(bot, QQ_Bot):
        user = dict_get_or_set_user_info(platform, user_id)
        if user.push_cnt < 3:
            logger.info(f'is_playing: {is_playing}')
            if is_playing:
                msg = ''
                if user.push_cnt < 5:
                    msg = "正在游玩时可以 /push 开启推送模式~"
                    await bot_send(bot, event, msg)


async def get_last_battle_or_coop(bot, event, for_push=False, get_battle=False, get_coop=False,
                                  get_equip=False,
                                  idx=0, get_screenshot=False, mask=False, get_player_code_idx=0):
    """获取最近全部对战或打工数据"""
    platform = bot.adapter.get_name()
    user_id = event.get_user_id()
    user = dict_get_or_set_user_info(platform, user_id)
    splatoon = Splatoon(bot, event, user)
    battle_t = ""
    coop_t = ""

    # 更新平台用户名
    event_info = await get_event_info(bot, event)
    user_name = event_info.get('user_name', "")
    # 更新缓存
    if user_name:
        user = dict_get_or_set_user_info(platform, user_id, user_name=user_name)

    if get_coop:
        get_battle = False

    if not get_coop:
        # idx为0情况下直接获取最新对战id
        # if idx == 0:
        # # 获取最新一场对战的id
        # res = await splatoon.get_last_one_battle()
        # if not res:
        #     # 再次尝试一次
        #     res = await splatoon.get_last_one_battle()
        #     if not res:
        #         return f'`bot网络错误，请稍后再试.`', False
        # b_info = res['data']['vsResult']['historyGroups']['nodes'][0]['historyDetails']['nodes'][0]
        # # 这个b_info实际上不完整，可用信息只有battle_id和mode，但响应速度整体都低于查询最近对战信息
        # battle_id = b_info['id']
        # battle_t = get_battle_time_or_coop_time(battle_id)
        # else:

        # 获取最近全部对战
        try:
            res = await splatoon.get_recent_battles()
            if not res:
                # 再次尝试一次
                res = await splatoon.get_recent_battles(multiple=True)
                if not res:
                    if for_push:
                        # 跳过本次循环
                        raise ValueError('no recent_battles')
                    else:
                        return f"`bot网络错误，请稍后再试.`", False
            b_info = res['data']['latestBattleHistories']['historyGroups']['nodes'][0]['historyDetails']['nodes'][idx]
            battle_id = b_info['id']
            battle_t = get_battle_time_or_coop_time(battle_id)
        except ValueError as e:
            if for_push:
                # 跳过本次循环
                raise e
            else:
                return f"`bot网络错误，请稍后再试.`", False
        except Exception as e:
            b_info = {}
            battle_id = ""
            battle_t = ""

    if not get_battle:
        # 获取最近全部打工
        try:
            res = await splatoon.get_coops()
            if not res:
                # 再次尝试一次
                res = await splatoon.get_coops(multiple=True)
                if not res:
                    if for_push:
                        # 跳过本次循环
                        raise ValueError('no coops')
                    else:
                        return f"`bot网络错误，请稍后再试.`", False

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
                else:
                    break
            if idx > coop_total_count:
                msg = "查询索引超出最大打工历史记录，请用更小索引重试，或使用/last b指定为对战模式重新进行查询"
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
        except ValueError as e:
            if for_push:
                # 跳过本次循环
                raise e
            else:
                return f"`bot网络错误，请稍后再试.`", False
        except Exception:
            coop_info = {}
            coop_id = ""
            coop_t = ""

    # 未指定模式下
    if (not get_coop) and (not get_battle):
        if coop_id and battle_id:
            # 看是否都取到值
            if battle_t > coop_t:
                get_battle = True
            else:
                get_battle = False
        else:
            if for_push:
                # 跳过本次循环
                raise ValueError('NetConnectError')
            else:
                # last等正常请求
                return f"`bot网络错误，请稍后再试.`", False

    # 计算是否正在游玩
    str_time = max(battle_t, coop_t)
    str_time = str_time.replace('T', ' ').replace('Z', '')
    dt_time = dt.strptime(str_time, '%Y%m%d %H%M%S')
    if dt.utcnow() - dt_time <= timedelta(minutes=20):
        is_playing = True
    else:
        is_playing = False

    if get_battle:
        # 获取对战数据
        if for_push:
            return battle_id, b_info, True, is_playing
        msg = await get_last_msg(splatoon, battle_id, b_info, idx=idx, is_battle=True, get_equip=get_equip,
                                 get_screenshot=get_screenshot, mask=mask, get_player_code_idx=get_player_code_idx)
        if get_player_code_idx:
            # 为top提供服务
            return msg
        # 关闭连接池
        await splatoon.req_client.close()
        return msg, is_playing
    else:
        # 获取打工数据
        if for_push:
            return coop_id, coop_info, False, is_playing
        msg = await get_last_msg(splatoon, coop_id, coop_info, idx=idx, is_battle=False, get_equip=get_equip,
                                 get_screenshot=get_screenshot, mask=mask)
        # 关闭连接池
        await splatoon.req_client.close()
        return msg, is_playing


async def get_last_msg(splatoon: Splatoon, _id, extra_info, idx=0, is_battle=True, get_equip=False,
                       get_screenshot=False, mask=False,
                       push_statistics=None, get_player_code_idx: int = 0):
    # 获取最后对战或打工的md文本
    try:
        if is_battle:
            if get_screenshot:
                try:
                    url = f"{SPLATNET3_URL}/history/detail/{_id}?lang=zh-CN"
                    pic = await get_app_screenshot(splatoon.platform, splatoon.user_id, url=url, mask=mask)
                except Exception as e:
                    logger.exception(e)
                    pic = None
                return pic
            battle_detail = await splatoon.get_battle_detail(_id)
            if not battle_detail:
                battle_detail = await splatoon.get_battle_detail(_id)

            # 为top命令提供player_code和name
            if get_player_code_idx:
                battle_detail = battle_detail['data']['vsHistoryDetail'] or {}
                teams = [battle_detail['myTeam']] + battle_detail['otherTeams']
                p_lst = []
                for t in sorted(teams, key=lambda x: x['order']):
                    for p in t['players']:
                        p_lst.append(p)

                if int(get_player_code_idx) > 0:
                    _idx = int(get_player_code_idx) - 1
                    _idx = min(_idx, len(p_lst))
                    p = p_lst[_idx]
                    player_code, player_name = get_game_sp_id_and_name(p)
                    return player_code, player_name
                else:
                    ret = []
                    for p in p_lst:
                        player_code, player_name = get_game_sp_id_and_name(p)
                        ret.append((player_code, player_name))
                    return ret

            # 取用户本人game_sp_id
            if not splatoon.user_db_info.game_sp_id or not splatoon.user_db_info.game_name:
                my_team = battle_detail['data']['vsHistoryDetail']['myTeam']
                p = {}
                for _p in my_team['players']:
                    if _p.get('isMyself'):
                        p = _p
                        break
                game_sp_id, game_name = get_game_sp_id_and_name(p)
                splatoon.set_user_info(game_sp_id=game_sp_id, game_name=game_name)

            msg = await get_battle_msg_md(extra_info, battle_detail, idx=idx, splatoon=splatoon, get_equip=get_equip,
                                          mask=mask, push_statistics=push_statistics)
        else:
            if get_screenshot:
                try:
                    url = f"{SPLATNET3_URL}/coop/{_id}?lang=zh-CN"
                    pic = await get_app_screenshot(splatoon.platform, splatoon.user_id, url=url, mask=mask)
                except Exception as e:
                    logger.exception(e)
                    pic = None
                return pic
            coop_detail = await splatoon.get_coop_detail(_id)
            if not coop_detail:
                coop_detail = await splatoon.get_coop_detail(_id)
            # 查询全部boss击杀数量
            coop_statistics_res = await splatoon.get_coop_statistics()
            coop_defeat = get_coop_defeat_statistics(coop_statistics_res)
            msg = await get_coop_msg_md(extra_info, coop_detail, coop_defeat, mask=mask, splatoon=splatoon,
                                        push_statistics=push_statistics)

    except Exception as e:
        logger.exception(e)
        msg = f'bot网络错误，获取最近 {"对战" if is_battle else "打工"}数据失败，请稍后再试'
    return msg


def get_coop_defeat_statistics(coop_statistics_res) -> dict:
    """获取boss击杀统计"""
    coop_statistics_res = coop_statistics_res["data"]["coopRecord"]
    defeat_enemy_records = coop_statistics_res["defeatEnemyRecords"]
    defeat_boss_records = coop_statistics_res["defeatBossRecords"]

    def arrange_defeat(nodes: list) -> dict:
        """整理击杀数据"""
        records = {}
        for node in nodes:
            k = node["enemy"]["name"]
            v = str(node["defeatCount"])
            records.update({k: v})
        return records

    coop_defeat_statistics = {"defeat_enemy": arrange_defeat(defeat_enemy_records),
                              "defeat_boss": arrange_defeat(defeat_boss_records)}
    return coop_defeat_statistics
