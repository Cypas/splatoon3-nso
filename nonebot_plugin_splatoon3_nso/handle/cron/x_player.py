import base64
import datetime
import json
import time
from datetime import datetime as dt

from ..send_msg import cron_notify_to_channel
from ...data.data_source import model_delete_top_player, model_delete_top_all, model_add_top_player, model_add_top_all, \
    model_get_newest_user, dict_get_or_set_user_info
from ...s3s.splatoon import Splatoon
from .utils import cron_logger
from ...utils import convert_td


async def get_x_player():
    """获取x赛数据"""
    cron_msg = f"get_x_player start"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("get_x_player", "start")
    t = datetime.datetime.utcnow()

    db_user = model_get_newest_user()
    if not db_user:
        cron_logger.info(f"no user login.")
        return
    user = dict_get_or_set_user_info(db_user.platform, db_user.user_id)
    splatoon = Splatoon(None, None, user)

    # top_id是每个赛季日服美服的选择id
    # for top_id in ('WFJhbmtpbmdTZWFzb24tcDoy', 'WFJhbmtpbmdTZWFzb24tYToy'):  # season-2
    # for top_id in ('WFJhbmtpbmdTZWFzb24tcDoz', 'WFJhbmtpbmdTZWFzb24tYToz'):  #season-3
    # for top_id in ('WFJhbmtpbmdTZWFzb24tcDo0', 'WFJhbmtpbmdTZWFzb24tYTo0'):  #season-4
    # for top_id in ('WFJhbmtpbmdTZWFzb24tcDo1', 'WFJhbmtpbmdTZWFzb24tYTo1'):  #season-5
    #for top_id in ('WFJhbmtpbmdTZWFzb24tcDo2', 'WFJhbmtpbmdTZWFzb24tYTo2'):  # season-6

    d1 = dt.utcnow()
    d2 = dt(2022, 3, 1)
    diff_month = (d1.year - d2.year) * 12 + d1.month - d2.month
    _season = diff_month // 3 - 1
    cron_logger.info(f'_season: {_season}')
    _lst = [f'XRankingSeason-p:{_season}', f'XRankingSeason-a:{_season}']
    for top_id in [base64.b64encode(s.encode()).decode('utf-8') for s in _lst]:
        await parse_x_data(top_id, splatoon)

    # 关闭连接池
    await splatoon.req_client.close()
    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = f"get_x_player end. {datetime.datetime.utcnow() - t}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("get_x_player", "end", f"耗时:{str_time}")


async def parse_x_data(top_id, splatoon):
    """整理x赛不同模式hash"""
    model_delete_top_player(top_id)
    model_delete_top_all(top_id)
    first_rows = await get_x_items(top_id, splatoon)

    for _t in (
            ('Ar', '0dc7b908c6d7ad925157a7fa60915523dab4613e6902f8b3359ae96be1ba175f'),
            ('Lf', 'ca55206629f2c9fab38d74e49dda3c5452a83dd02a5a7612a2520a1fc77ae228'),
            ('Gl', '6ab0299d827378d2cae1e608d349168cd4db21dd11164c542d405ed689c9f622'),
            ('Cl', '485e5decc718feeccf6dffddfe572455198fdd373c639d68744ee81507df1a48')
    ):
        x_type, hash_mode = _t
        try:
            await get_top_x(first_rows, top_id, x_type, hash_mode, splatoon)
        except Exception as ex:
            cron_logger.exception(f'get_top_x error: {top_id}, {x_type}, error:{ex}')
            continue
        time.sleep(5)


async def get_top_x(data_row, top_id, x_type, mode_hash, splatoon=None):
    """获取500强数据"""
    cron_logger.info(f'get_top_x: {top_id}, {x_type}')
    res = data_row
    if not res:
        return

    top_type = base64.b64decode(top_id).decode('utf-8')
    for n in res['data']['xRanking'][f'xRanking{x_type}']['edges']:
        parse_x_row(n, top_type, x_type, top_id)

    has_next_page = res['data']['xRanking'][f'xRanking{x_type}']['pageInfo']['hasNextPage']
    cursor = res['data']['xRanking'][f'xRanking{x_type}']['pageInfo']['endCursor']
    while True:
        if not has_next_page:
            break

        _d = {
            "extensions": {"persistedQuery": {"sha256Hash": mode_hash, "version": 1}},
            "variables": {'cursor': cursor, 'first': 25, 'page': 1, 'id': top_id}
        }
        _d = json.dumps(_d)
        _res = await splatoon.get_custom_data(_d)
        for n in _res['data']['node'][f'xRanking{x_type}']['edges']:
            parse_x_row(n, top_type, x_type, top_id)

        cursor = _res['data']['node'][f'xRanking{x_type}']['pageInfo']['endCursor']
        has_next_page = _res['data']['node'][f'xRanking{x_type}']['pageInfo']['hasNextPage']
        cron_logger.info(f'get page:  {cursor}, {has_next_page}')
        if not has_next_page:
            break

    for page in (2, 3, 4, 5):
        _d = {
            "extensions": {"persistedQuery": {"sha256Hash": mode_hash, "version": 1}},
            "variables": {'cursor': None, 'first': 25, 'page': page, 'id': top_id}
        }
        _d = json.dumps(_d)
        _res = await splatoon.get_custom_data(_d)

        for n in _res['data']['node'][f'xRanking{x_type}']['edges']:
            parse_x_row(n, top_type, x_type, top_id)

        cursor = _res['data']['node'][f'xRanking{x_type}']['pageInfo']['endCursor']
        has_next_page = _res['data']['node'][f'xRanking{x_type}']['pageInfo']['hasNextPage']
        while True:
            if not has_next_page:
                break
            _d = {
                "extensions": {"persistedQuery": {"sha256Hash": mode_hash, "version": 1}},
                "variables": {'cursor': cursor, 'first': 25, 'page': page, 'id': top_id}
            }
            _d = json.dumps(_d)
            _res = await splatoon.get_custom_data(_d)
            for n in _res['data']['node'][f'xRanking{x_type}']['edges']:
                parse_x_row(n, top_type, x_type, top_id)

            cursor = _res['data']['node'][f'xRanking{x_type}']['pageInfo']['endCursor']
            has_next_page = _res['data']['node'][f'xRanking{x_type}']['pageInfo']['hasNextPage']

            cron_logger.info(f'get page:  {cursor}, {has_next_page}')
            if not has_next_page:
                break


async def get_x_items(top_id, splatoon):
    """获取X排行榜第一屏数据"""
    res = await splatoon.get_x_ranking_500(top_id)
    return res


def parse_x_row(n, top_type, x_type, top_id):
    """处理一行x数据"""
    n = n['node']
    name = n['name']
    name_id = n['nameId']
    rank = n['rank']
    power = n['xPower']
    byname = n['byname']
    weapon = n['weapon']['name']
    p_id = base64.b64decode(n['id']).decode('utf-8')
    player_code = p_id.split('-')[-1]
    _top_type = f'{top_type}:{x_type}'
    weapon_id = int(base64.b64decode(n['weapon']['id']).decode('utf-8').split('-')[-1])

    row = [top_id, _top_type, rank, power, name, name_id, player_code, byname, weapon_id, weapon]
    # logger.info(row[:-1])
    model_add_top_player(row)
    row.append(dt.utcnow())
    model_add_top_all(row)
