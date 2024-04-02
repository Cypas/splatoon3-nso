import base64
import datetime
from datetime import datetime as dt

from ..send_msg import cron_notify_to_channel
from ...data.data_source import model_delete_top_all, model_add_top_all, \
    model_get_newest_user, dict_get_or_set_user_info, model_get_top_all_count_by_top_type
from ...s3s.splatoon import Splatoon
from .utils import cron_logger
from ...utils import convert_td


async def get_event_top():
    """获取活动排行榜人员"""
    cron_msg = f"get_event_top start"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("get_event_top", "start")
    t = dt.utcnow()

    db_user = model_get_newest_user()
    if not db_user:
        cron_logger.info(f"no user login.")
        return
    user = dict_get_or_set_user_info(db_user.platform, db_user.user_id)
    splatoon = Splatoon(None, None, user)
    # 执行任务
    try:
        await get_event_top_player_task(splatoon)
    except Exception as e:
        cron_logger.info(f"get_event_top error:{e}")
    finally:
        # 关闭连接池
        await splatoon.req_client.close()
    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = f"get_event_top end {str_time}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("get_event_top", "end", f"耗时:{str_time}")


async def get_event_top_player_task(splatoon):
    """任务:获取活动排行榜"""
    res = await splatoon.get_event_list()
    if not res:
        return
    edges = res['data']['leagueMatchRankingSeasons']['edges']
    for n in edges[::-1]:
        in_ed = n['node']['leagueMatchRankingTimePeriodGroups']['edges']
        for nn in in_ed[::-1]:
            cron_logger.info(nn['node']['leagueMatchSetting']['leagueMatchEvent']['name'])
            for t in nn['node']['timePeriods']:
                top_id = t['id']
                top_type = base64.b64decode(top_id).decode('utf-8')
                _, search_type = top_type.split('TimePeriod-')
                count = model_get_top_all_count_by_top_type(search_type)
                cron_logger.info(f'top_all.type search {search_type}, {count or 0}')
                if count:
                    continue
                res = await splatoon.get_event_items(top_id, multiple=True)
                parse_league(res)


def parse_league(league):
    """解析活动榜单并写入数据"""
    if not league:
        cron_logger.info('no league')
        return

    play_time = league['data']['rankingPeriod']['endTime'].replace('T', ' ').replace('Z', '')
    play_time = dt.strptime(play_time, '%Y-%m-%d %H:%M:%S')
    league_name = league['data']['rankingPeriod']['leagueMatchSetting']['leagueMatchEvent']['name']
    cron_logger.info(f'{play_time}, {league_name}')
    for team in league['data']['rankingPeriod']['teams']:
        top_id = team['id']
        cron_logger.info(f'saving top_id: {top_id}')
        model_delete_top_all(top_id)
        top_type = base64.b64decode(top_id).decode('utf-8')
        for n in team['details']['nodes']:
            for player in n['players']:
                player_id = player['id']
                player_code = base64.b64decode(player_id).decode('utf-8').split(':')[-1][2:]
                weapon_id = int(base64.b64decode(player['weapon']['id']).decode('utf-8').split('-')[-1])
                weapon = player['weapon']['name']
                db_row = [top_id, top_type, n['rank'], n['power'], player['name'], player['nameId'], player_code,
                          player['byname'], weapon_id, weapon, play_time]
                model_add_top_all(db_row)
