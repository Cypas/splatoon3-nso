from nonebot import logger
from playwright.async_api import async_playwright

from .utils import SPLATNET3_URL

COOKIES = [{'name': '_gtoken', 'value': 'undefined', 'domain': 'api.lp1.av5ja.srv.nintendo.net', 'path': '/',
            'expires': -1, 'httpOnly': False, 'secure': False, 'sameSite': 'Lax'}]


async def get_app_screenshot(gtoken, key='', url='', mask=False):
    """获取app页面截图"""
    logger.info(f'get_app_screenshot： {len(gtoken)}, {key}, {url}')
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        cookies = COOKIES[:]
        cookies[0]['value'] = gtoken
        height = 1000
        for _k in ('对战', '涂地', '蛮颓', 'X', '活动', '私房', '武器', '鲑鱼跑', '徽章'):
            if _k in key:
                height = 2500
        if mask:
            height = 740
        if url and 'coop' in url or key == '打工':
            height = 1500
        context = await browser.new_context(viewport={"width": 500, "height": height})
        await context.add_cookies(cookies)
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
            await page.goto(f"{SPLATNET3_URL}/?lang=zh-CN")
            # await page.wait_for_timeout(1000)
            url = f"{SPLATNET3_URL}/history_record/summary"

            _d = {
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

            for k, v in _d.items():
                if k in key:
                    url = f"{SPLATNET3_URL}/{v}"
                    break

            if '问卷' in key:
                url = f"{SPLATNET3_URL}/fest_record"

            await page.goto(f"{url}?lang=zh-CN")

        # key = [] if not key else key.split(' ')
        # for k in key:
        #     await page.get_by_text(k, exact=True).nth(0).click()

        if '问卷' in key:
            k = '问卷实施中'
            await page.get_by_text(k, exact=True).nth(0).click()

        await page.wait_for_timeout(6000)
        img_raw = await page.screenshot(full_page=True)

    return img_raw
