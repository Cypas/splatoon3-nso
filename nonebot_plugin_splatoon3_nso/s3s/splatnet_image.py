import playwright
from nonebot import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, ViewportSize

from .utils import SPLATNET3_URL
from ..data.utils import GlobalUserInfo
from ..utils import proxies, get_msg_id

global_browser = None
global_dict_context = {}


async def get_app_screenshot(user: GlobalUserInfo, key='', url='', mask=False):
    """获取app页面截图"""
    msg_id = get_msg_id(user.platform, user.user_id)
    logger.info(f'get_app_screenshot： {msg_id}, {key}, {url}')

    COOKIES = [{'name': '_gtoken', 'value': 'undefined', 'domain': 'api.lp1.av5ja.srv.nintendo.net', 'path': '/',
                'expires': -1, 'httpOnly': False, 'secure': False, 'sameSite': 'Lax'}]
    cookies = COOKIES[:]
    cookies[0]['value'] = user.g_token
    # 要保留context的情况下，无法重新设定height，只能初始化为最大值2500
    # height = 1000
    # for _k in ('对战', '涂地', '蛮颓', 'X', '活动', '私房', '武器', '鲑鱼跑', '徽章'):
    #     if _k in key:
    #         height = 2500
    # if mask:
    #     height = 740
    # if url and 'coop' in url or key == '打工':
    #     height = 1500
    # viewport = ViewportSize({"width": 500, "height": height})

    # 取上下文对象
    context = await init_or_get_context(msg_id, cookies)
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
            '对战': 'history/latest',
            '涂地': 'history/regular',
            '蛮颓': 'history/bankara',
            'X': 'history/xmatch',
            '活动': 'history/event',
            '私房': 'history/private',
            '武器': 'weapon_record',
            '徽章': 'history_record/badge',
            '鲑鱼跑': 'coop',
            '打工b': 'coop_record/enemies',
            '打工B': 'coop_record/enemies',
            '打工': 'coop_record/play_record',
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

        if '问卷' in key:
            url = f"{SPLATNET3_URL}/fest_record"

        await page.goto(f"{url}?lang=zh-CN")

    if '问卷' in key:
        k = '问卷实施中'
        await page.get_by_text(k, exact=True).nth(0).click()

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


async def init_or_get_context(msg_id, cookies=None) -> BrowserContext:
    """初始化或获取用户会话对应的 context"""
    global global_dict_context
    context = global_dict_context.get(msg_id)
    if context:
        return context
    else:
        browser = await get_browser()
        viewport = ViewportSize({"width": 500, "height": 2500})
        context = await browser.new_context(viewport=viewport)
        if cookies:
            await context.add_cookies(cookies)
        global_dict_context.update({msg_id: context})
        return context
