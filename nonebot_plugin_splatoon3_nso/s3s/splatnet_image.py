from nonebot import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, ViewportSize

from .utils import SPLATNET3_URL
from ..data.data_source import dict_get_or_set_user_info
from ..utils import proxies, get_msg_id

global_browser = None
global_dict_context = {}


async def get_app_screenshot(platform, user_id, key: str = "", url="", mask=False):
    """获取app页面截图"""
    user = dict_get_or_set_user_info(platform, user_id)
    msg_id = get_msg_id(platform, user_id)
    logger.info(f'get_app_screenshot： {msg_id}, {key}, {url}')

    COOKIES = [{'name': '_gtoken', 'value': 'undefined', 'domain': 'api.lp1.av5ja.srv.nintendo.net', 'path': '/',
                'expires': -1, 'httpOnly': False, 'secure': False, 'sameSite': 'Lax'}]
    cookies = COOKIES[:]
    cookies[0]['value'] = user.g_token
    height = 1000
    _type = "default"
    # 列表类
    for _k in ('最近', '涂地', '蛮颓', 'X', 'x', 'X赛', 'x赛', '活动', '私房', '武器', '打工', '鲑鱼跑', '徽章'):
        if _k in key:
            height = 2500
            _type = "list"
            break
    if url and mask:
        # 对战打码且隐藏奖牌
        height = 740
        _type = "battle_mask"
    if 'coop' in url:
        height = 1500
        _type = "coop_detail"
    viewport = ViewportSize({"width": 500, "height": height})

    # 取上下文对象
    context = await init_or_get_context(msg_id, cookies, _type=_type, viewport=viewport)
    page = await context.new_page()

    if url:
        await page.goto(url)
        if mask and url and 'detail' in url:
            await page.locator('"WIN!"').nth(0).click()
            await page.locator('"LOSE..."').nth(0).click()
        if mask and url and 'coop' in url:
            for _r in ('"Clear!!"', '"Failure"'):
                try:
                    await page.locator(_r).nth(0).click()
                except:
                    pass
    else:
        # 先进入首页(对于请求来说没必要模拟这一步)
        # await page.goto(f"{SPLATNET3_URL}/?lang=zh-CN")
        # await page.wait_for_timeout(1000)
        trans = {
            '个人穿搭': 'my_outfits',
            '好友': 'friends',
            '最近': 'history/latest',
            '涂地': 'history/regular',
            '蛮颓': 'history/bankara',
            'X': 'history/xmatch',
            'x': 'history/xmatch',
            'X赛': 'history/xmatch',
            'x赛': 'history/xmatch',
            '活动': 'history/event',
            '私房': 'history/private',
            '武器': 'weapon_record',
            '徽章': 'history_record/badge',
            '打工': 'coop',
            '鲑鱼跑': 'coop',
            '打工记录': 'coop_record/play_record',
            '击倒数量': 'coop_record/enemies',
            '祭典': 'fest_record',
            '英雄': 'hero_record',
            '地图': 'stage_record',
        }
        # 未匹配，默认地址
        url = f"{SPLATNET3_URL}/history_record/summary"

        for k, v in trans.items():
            if k in key:
                url = f"{SPLATNET3_URL}/{v}"
                break

        if "问卷" in key or "投票" in key:
            url = f"{SPLATNET3_URL}/fest_record"

        await page.goto(f"{url}?lang=zh-CN")

    if "问卷" in key or "投票" in key:
        k = "问卷实施中"
        locator = page.get_by_text(k, exact=True)
        if not await locator.count():
            raise ValueError("text not found")
        else:
            await locator.nth(0).click()

    await page.wait_for_timeout(6000)
    img_raw = await page.screenshot(full_page=True)
    await page.close()

    return img_raw


async def init_browser() -> Browser:
    """初始化 browser 并唤起"""
    global global_browser
    p = await async_playwright().start()
    # 代理
    if proxies:
        proxy = {"server": proxies}
        # 代理访问
        global_browser = await p.chromium.launch(proxy=proxy)
    else:
        global_browser = await p.chromium.launch()
    return global_browser


async def get_browser() -> Browser:
    """获取目前唤起的 browser"""
    global global_browser
    if global_browser is None or not global_browser.is_connected():
        global_browser = await init_browser()

    return global_browser


async def init_or_get_context(msg_id, cookies=None, _type: str = "",
                              viewport: ViewportSize = None) -> BrowserContext:
    """初始化或获取用户会话对应的 context"""
    global global_dict_context
    context_info = global_dict_context.get(msg_id)
    if context_info and context_info.get(_type):
        context = context_info.get(_type)
        return context
    else:
        browser = await get_browser()
        context = await browser.new_context(viewport=viewport)
        if cookies:
            await context.add_cookies(cookies)
        context_info = {_type: context}
        global_dict_context.update({msg_id: context_info})
        return context