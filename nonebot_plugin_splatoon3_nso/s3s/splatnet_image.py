import asyncio
import playwright
from nonebot import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, ViewportSize, Playwright

from .iksm import S3S
from .splatoon import Splatoon
from .utils import SPLATNET3_URL
from .. import plugin_config
from ..data.data_source import dict_get_or_set_user_info, model_get_or_set_user
from ..utils import global_proxies, get_msg_id
from ..utils.http import AsHttpReq  # 导入AsHttpReq类，复用其代理检测功能

# 全局浏览器及管理变量（新增内存管理相关）
global_browser: Browser = None
global_playwright: Playwright = None  # 用于彻底关闭Playwright实例
global_dict_ss_user: dict = {}

# 代理状态跟踪
_browser_using_proxy: bool = False  # 当前浏览器是否使用代理
_last_proxy_check_time: float = 0  # 上次代理检测时间


async def get_app_screenshot(splatoon: Splatoon, key: str = "", url="", mask=False) -> str | bytes:
    """获取app页面截图（仅优化内存释放版本）"""
    ### nso截图需要的是gtoken(3h)，home页面校验的是bullet_token(2h)
    # 就会存在说g_token已过期，但home页面校验通过的情况，此时截图nso仍会无数据(可能gtoken未正确刷新，或redis跳过了gtoken获取)
    # 稳定验证 需要去校验gtoken的jwt是否过期

    user = dict_get_or_set_user_info(splatoon.platform, splatoon.user_id)
    g_token = user.g_token

    msg_id = get_msg_id(splatoon.platform, splatoon.user_id)
    logger.info(f'get_app_screenshot： {msg_id}, {key}, {url}')

    COOKIES = [{'name': '_gtoken', 'value': 'undefined', 'domain': 'api.lp1.av5ja.srv.nintendo.net', 'path': '/',
                'expires': -1, 'httpOnly': False, 'secure': False, 'sameSite': 'Lax'}]
    cookies = COOKIES[:]
    cookies[0]['value'] = g_token
    height = 1000
    _type = "default"

    # 列表类页面高度设置
    for _k in ('最近', '涂地', '蛮颓', 'X', 'x', 'X赛', 'x赛', '活动', '私房', '武器进度', '武器分数', '打工', '鲑鱼跑', '徽章',):
        if _k in key and key != "打工记录":
            height = 2500
            _type = "list"
            break
    if url and mask:
        # 对战打码且隐藏奖牌
        height = 740
        _type = "battle_mask"
    if 'coop' in url or key == "打工记录":
        height = 1500
        _type = "coop_detail"
    if key == "总览":
        height = 1200
    viewport = ViewportSize({"width": 500, "height": height})

    # 获取上下文对象
    context = await init_context(cookies=cookies, viewport=viewport)

    # 更新使用次数计数
    ss_user = global_dict_ss_user.get(msg_id)
    if ss_user:
        # ss计数+1
        global_dict_ss_user.update({msg_id: ss_user + 1})
    else:
        global_dict_ss_user.update({msg_id: 1})

    page = await context.new_page()

    try:
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

            # 未匹配，默认地址
            # url = f"{SPLATNET3_URL}/history/latest"
            for k, v in ss_url_trans.items():
                if k in key:
                    url = f"{SPLATNET3_URL}/{v}"
                    break

            if "问卷" in key or "投票" in key:
                url = f"{SPLATNET3_URL}/fest_record"

            await page.goto(f"{url}?lang=zh-CN")

        # 页面加载等待
        if "武器" in key or "徽章" in key:
            # 武器页面等待更长时间
            await page.wait_for_load_state(state="networkidle")
            await page.wait_for_timeout(5000)
        else:
            await page.wait_for_load_state(state="networkidle")
            await page.wait_for_timeout(2000)

        if "问卷" in key or "投票" in key:
            k = "问卷实施中"
            locator = page.get_by_text(k, exact=True)
            if await locator.count():
                await locator.nth(0).click()
                await page.wait_for_load_state(state="networkidle")
                await page.wait_for_timeout(6000)

        # 截图
        img_raw = await page.screenshot(full_page=True)
    except playwright.async_api.TimeoutError:
        return "nso截图超时"
    except Exception as e:
        return f"nso截图错误:{e}"
    finally:
        # 关键优化1：确保页面和上下文彻底关闭
        await page.close()  # 先关闭页面释放渲染资源
        await context.close()  # 再关闭上下文

    return img_raw


ss_url_trans = {
    '个人穿搭': 'my_outfits',
    '好友': 'friends',
    '最近': 'history/latest',
    '涂地': 'history/regular',
    '蛮颓': 'history/bankara',
    '真格': 'history/bankara',
    '挑战': 'history/bankara',
    '开放': 'history/bankara',
    'X赛': 'history/xmatch',
    'x赛': 'history/xmatch',
    'X': 'history/xmatch',
    'x': 'history/xmatch',
    '活动': 'history/event',
    '私房': 'history/private',
    '武器进度': 'weapon/collection',
    '武器分数': 'weapon/data',
    '徽章': 'history_record/badge',
    '打工记录': 'coop_record/play_record',
    '打工': 'coop',
    '鲑鱼跑': 'coop',
    '击倒数量': 'coop_record/enemies',
    '击杀数量': 'coop_record/enemies',
    '祭典': 'fest_record',
    '祭奠': 'fest_record',
    '英雄模式': 'hero_record',
    '英雄': 'hero_record',
    '地图': 'stage_record',
    '总览': 'history_record/summary',
}


async def check_proxy_available() -> bool:
    """
    检测代理是否可用，复用AsHttpReq类中的代理检测逻辑
    :return: True=可用，False=不可用
    """
    return await AsHttpReq.is_proxy_available()


async def init_browser() -> Browser:
    """初始化浏览器（优化：管理Playwright实例生命周期 + 代理自动切换）"""
    global global_browser, global_playwright, _browser_using_proxy, _last_proxy_check_time
    # 关键优化2：先关闭旧的Playwright实例，避免进程残留
    if global_playwright is not None:
        await global_playwright.stop()
    # 重新启动Playwright
    global_playwright = await async_playwright().start()

    browser_args = [
        # 设置默认字体
        '--default-font-family="Noto Sans CJK"',
    ]

    proxy = None
    use_proxy = False
    
    # 代理处理
    if global_proxies:
        # 检测代理是否可用
        proxy_available = await check_proxy_available()
        _last_proxy_check_time = asyncio.get_event_loop().time()  # 记录检测时间
        
        if proxy_available:
            if plugin_config.splatoon3_proxy_list_mode:
                # bypass 忽略部分域名
                proxy = {"server": global_proxies,
                         # "bypass": "api.lp1.av5ja.srv.nintendo.net"
                         }
                use_proxy = True
            else:
                # 全局代理访问
                proxy = {"server": global_proxies}
                use_proxy = True
        else:
            logger.info("代理不可用，使用直连模式启动浏览器")

    # 更新浏览器代理状态
    _browser_using_proxy = use_proxy
    
    # 启动浏览器
    if use_proxy:
        global_browser = await global_playwright.chromium.launch(proxy=proxy, args=browser_args)
        logger.info(f"浏览器已启动，使用代理: {global_proxies}")
    else:
        global_browser = await global_playwright.chromium.launch(args=browser_args)
        logger.info("浏览器已启动，使用直连模式")
    
    return global_browser


async def get_browser() -> Browser:
    """获取浏览器实例（优化：定期重启释放内存 + 代理状态检查）"""
    global global_browser, _browser_using_proxy
    
    # 检查浏览器是否需要重启
    need_restart = False
    
    if global_browser is None or not global_browser.is_connected():
        need_restart = True
    
    # 检查代理状态是否变化（如果有代理配置）
    if global_proxies and not need_restart:
        proxy_available = await check_proxy_available()
        # 检查当前浏览器是否使用代理（通过检查global_proxies是否为None来判断）
        # 这里我们简化处理：如果代理状态变化，就重启浏览器
        # 注意：这种方式在频繁切换代理时可能会有性能问题，但能保证代理状态的一致性
        
        # 检查代理状态是否发生变化
        # 情况1: 当前使用代理，但代理变得不可用
        if _browser_using_proxy and not proxy_available:
            logger.info("代理状态变化（不可用），将重启浏览器切换到直连模式")
            need_restart = True
        # 情况2: 当前使用直连，但代理变得可用
        elif not _browser_using_proxy and proxy_available:
            logger.info("代理状态变化（可用），将重启浏览器切换到代理模式")
            need_restart = True
    
    if need_restart:
        await cleanup_browser()  # 确保清理旧实例
        global_browser = await init_browser()

    return global_browser


async def init_context(cookies=None, viewport: ViewportSize = None) -> BrowserContext:
    """初始化上下文（优化：禁用缓存减少内存占用）"""
    browser = await get_browser()
    # 关键优化4：禁用缓存，减少内存占用
    context = await browser.new_context(
        viewport=viewport,
        accept_downloads=False  # 禁用下载功能
    )
    if cookies:
        await context.add_cookies(cookies)
    return context


# 在 splatnet_image.py 中添加资源清理
async def cleanup_browser():
    global global_browser, global_playwright
    if global_browser:
        await global_browser.close()
    if global_playwright:
        await global_playwright.stop()
    global_browser = None
    global_playwright = None
