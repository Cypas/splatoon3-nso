import asyncio
import base64
import random
import time
from datetime import datetime as dt
import os
import json
import subprocess

from ...data.db_sqlite import UserTable
from ...config import plugin_config
from ...s3s.iksm import F_GEN_URL_2, F_GEN_URL
from ...utils import proxy_address, convert_td
from ...utils.utils import DIR_RESOURCE, init_path
from ...data.data_source import model_get_all_stat_user
from ..send_msg import notify_to_private, report_notify_to_channel, cron_notify_to_channel
from .utils import user_remove_duplicates, cron_logger
from ...utils.bot import Kook_ActionFailed


async def sync_stat_ink():
    """同步至stat"""
    cron_msg = f"sync_stat_ink start"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("sync_stat_ink", "start")
    t = dt.utcnow()

    # 更新s3sti脚本
    await update_s3si_ts()

    db_users = model_get_all_stat_user()
    # 去重
    db_users = user_remove_duplicates(db_users)

    complete_cnt = 0
    upload_cnt = 0
    error_cnt = 0
    else_error_cnt = 0
    notice_error_cnt = 0
    _pool = 10
    for i in range(0, len(db_users), _pool):
        pool_users_list = db_users[i:i + _pool]
        tasks = [sync_stat_ink_func(db_user) for db_user in pool_users_list]
        res = await asyncio.gather(*tasks)
        for r in res:
            is_complete, is_upload, is_error, is_notice_error, is_else_error = r
            if is_complete:
                complete_cnt += 1
            if is_upload:
                upload_cnt += 1
            if is_error:
                error_cnt += 1
            if is_notice_error:
                notice_error_cnt += 1
            if is_else_error:
                else_error_cnt += 1
    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = (f"sync_stat_ink end: {str_time}\n"
                f"complete_cnt: {complete_cnt}, upload_cnt: {upload_cnt}\n"
                f"error_cnt: {error_cnt},notice_error_cnt: {notice_error_cnt},else_error_cnt: {else_error_cnt}")
    cron_logger.info(cron_msg)
    notice_msg = (f"耗时:{str_time}\n完成: {complete_cnt},同步: {upload_cnt}\n"
                  f"错误: {error_cnt},通知错误: {notice_error_cnt},配置错误: {else_error_cnt}")
    await cron_notify_to_channel("sync_stat_ink", "end", notice_msg)


async def sync_stat_ink_func(db_user: UserTable):
    """同步stat.ink"""
    is_complete, is_upload, is_error, is_else_error, is_notice_error = False, False, False, False, False

    cron_logger.debug(f"get user: {db_user.user_name}, have stat_key: {db_user.stat_key}")

    res = get_post_stat_msg(db_user)
    if not isinstance(res, tuple):
        is_else_error = True
        return is_complete, is_upload, is_error, is_notice_error, is_else_error

    msg, error_msg = res
    is_complete = True
    if msg:
        is_upload = True
        if db_user.stat_notify:
            cron_logger.debug(f"{db_user.id}, {db_user.user_name}, {msg}")
            # 通知到频道
            # await report_notify_to_channel(db_user.platform, db_user.user_id, msg, _type="job")
            # 通知到私信
            msg += "\n/stat_notify close 关闭stat.ink同步情况推送"
            try:
                await notify_to_private(db_user.platform, db_user.user_id, msg)
            except Exception as e:
                cron_logger.error(f"db_user_id:{db_user.user_id} private notice error: {e}")
                is_notice_error = True

    if error_msg:
        is_error = True

    return is_complete, is_upload, is_error, is_notice_error, is_else_error


def get_post_stat_msg(db_user):
    """获取同步消息文本"""

    cron_logger.debug(f"get user: {db_user.user_name}, have stat_key: {db_user.stat_key}")
    if not (db_user and db_user.session_token and db_user.stat_key):
        return

    # 两个f_api 负载均衡
    f_url_lst = [F_GEN_URL, F_GEN_URL_2]
    random.shuffle(f_url_lst)
    f_gen_url = f_url_lst[0]
    res = exported_to_stat_ink(db_user.id, db_user.session_token, db_user.stat_key, f_gen_url, g_token=db_user.g_token,
                               bullet_token=db_user.bullet_token)

    if not isinstance(res, tuple):
        return
    battle_cnt, coop_cnt, url, error_msg = res
    # f-api重试
    if error_msg:
        # 判断重试时的对象名称以及f地址
        if f_gen_url == F_GEN_URL:
            now_f_str = "F_URL"
            next_f_str = "F_URL_2"
            next_f_url = F_GEN_URL_2
        else:
            now_f_str = "F_URL_2"
            next_f_str = "F_URL"
            next_f_url = F_GEN_URL
        cron_logger.warning(f"{db_user.id}, {db_user.user_name}, {now_f_str} Error，try {next_f_str} again")
        res = exported_to_stat_ink(db_user.id, db_user.session_token, db_user.stat_key, next_f_url,
                                   g_token=db_user.g_token,
                                   bullet_token=db_user.bullet_token)

        if not isinstance(res, tuple):
            return
        battle_cnt, coop_cnt, url, error_msg = res

    msg = ""
    if battle_cnt or coop_cnt:
        msg = "> Exported"
        if battle_cnt:
            msg += f" {battle_cnt} battles"
        if coop_cnt:
            msg += f" {coop_cnt} jobs"

        if battle_cnt and not coop_cnt:
            url += "/spl3"
        elif coop_cnt and not battle_cnt:
            url += "/salmon3"
        msg += f" to\n{url}\n\n"

        log_msg = msg.replace("\n", "")
        cron_logger.info(f"{db_user.id}, {db_user.user_name}, {log_msg}")

    return msg, error_msg


async def update_s3si_ts():
    # 更新 s3si_ts 上传脚本
    cron_msg = f"update_s3si_ts start"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("update_s3si_ts", "start")
    t = dt.utcnow()

    path_folder = DIR_RESOURCE
    init_path(path_folder)
    os.chdir(path_folder)

    # 取消原有git代理
    os.system("git config --global --unset http.proxy")
    if proxy_address:
        # 设置git代理
        os.system(f"git config --global http.proxy {proxy_address}")

    # get s3s code
    s3s_folder = f"{path_folder}/s3sits_git"
    if not os.path.exists(s3s_folder):
        cmd = f"git clone https://github.com/spacemeowx2/s3si.ts {s3s_folder}"
        rtn = subprocess.run(cmd.split(' '), stdout=subprocess.PIPE).stdout.decode('utf-8')
        cron_logger.info(f"cli: {rtn}")
        os.chdir(s3s_folder)
    else:
        os.chdir(s3s_folder)
        os.system("git restore .")
        cmd = f"git pull"
        rtn = subprocess.run(cmd.split(' '), stdout=subprocess.PIPE).stdout.decode('utf-8')
        cron_logger.info(f'cli: {rtn}')

    # edit agent
    cmd_list = [
        """sed -i "1,5s/s3si.ts/s3si.ts - t.me\/splatoon3_bot/g" ./src/constant.ts""",
    ]
    for cmd in cmd_list:
        cron_logger.debug(f'cli: {cmd}')
        os.system(cmd)

    dir_user_configs = f'{s3s_folder}/user_configs'
    init_path(dir_user_configs)
    # 耗时
    str_time = f"{(dt.utcnow() - t).seconds}s"
    cron_msg = f"update_s3si_ts end, {str_time}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel("update_s3si_ts", "end", f"耗时:{str_time}")


def exported_to_stat_ink(user_id, session_token, api_key, f_gen_url, user_lang="zh-CN", g_token="", bullet_token=""):
    """同步战绩文件至stat.ink"""
    cron_logger.info(f'start exported_to_stat_ink: user_db_id:{user_id}')
    cron_logger.debug(f'session_token: {session_token}')
    cron_logger.debug(f'api_key: {api_key}')
    user_lang = user_lang or 'zh-CN'

    s3sits_folder = f'{DIR_RESOURCE}/s3sits_git'
    os.chdir(s3sits_folder)

    # 检查deno路径是否配置
    deno_path = plugin_config.splatoon3_deno_path
    if not deno_path or not os.path.exists(deno_path):
        cron_logger.info(f'deno_path not set: {deno_path or ""} '.center(120, '-'))
        return

    # 新建或修改配置项
    path_config_file = f'{s3sits_folder}/user_configs/config_{user_id}.json'
    if not os.path.exists(path_config_file):
        # 新建文件
        config_data = {
            "fGen": f_gen_url,
            "userLang": user_lang,
            "loginState": {
                "sessionToken": session_token,
                "gToken": g_token,
                "bulletToken": bullet_token,
            },
            "statInkApiKey": api_key
        }
        with open(path_config_file, 'w') as f:
            f.write(json.dumps(config_data, indent=2, sort_keys=False, separators=(',', ': ')))
    else:
        # 写入配置文件
        # fGen写入过程中 https://含有/ 会和控制符/冲突，此处控制符得改为#
        cmds = [
            f"""sed -i 's#fGen[^,]*,#fGen\": \"{f_gen_url}\",#' {path_config_file}""",
            f"""sed -i 's/userLang[^,]*,/userLang\": \"{user_lang}\",/' {path_config_file}""",
            f"""sed -i 's/sessionToken[^,]*,/sessionToken\": \"{session_token}\",/' {path_config_file}""",
            f"""sed -i 's/statInkApiKey[^,]*,/statInkApiKey\": \"{api_key}\",/' {path_config_file}""",
        ]
        if g_token and bullet_token:
            cmds.append(f"""sed -i 's/gToken[^,]*,/gToken\": \"{g_token}\",/' {path_config_file}""")
            cmds.append(f"""sed -i 's/bulletToken[^,]*,/bulletToken\": \"{bullet_token}\",/' {path_config_file}""")

        for cmd in cmds:
            cron_logger.debug(f'user_db_id:{user_id} cli: {cmd}')
            os.system(cmd)

    env = {}
    # deno代理配置
    # http
    if proxy_address:
        env.update({"HTTP_PROXY": f"http://{proxy_address}",
                    "HTTPS_PROXY": f"http://{proxy_address}"
                    })
    # no proxy
    if plugin_config.splatoon3_proxy_list_mode and proxy_address:
        env.update({"NO_PROXY": f"deno.land,api.lp1.av5ja.srv.nintendo.net"})

    # run deno
    cmd = f'{deno_path} run -Ar ./s3si.ts -n -p {path_config_file}'
    cron_logger.info(cmd)

    res = ""
    error = ""
    battle_cnt = 0
    coop_cnt = 0
    url = ''
    error_msg = ""

    try:
        rtn: subprocess.CompletedProcess[bytes] = subprocess.run(cmd.split(' '), stdout=subprocess.PIPE,
                                                                 stderr=subprocess.PIPE, env=env, timeout=300)
        res = rtn.stdout.decode('utf-8')
        error = rtn.stderr.decode('utf-8')
    except subprocess.TimeoutExpired:
        error_msg = f"deno run timeout\n"
    except Exception as e:
        error_msg = f"deno run err:\n{e}"
    if error:
        # error里面混有deno debug内容，需要经过过滤
        for line in error.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 输出内容加了供终端显示颜色的ascii码，将其转化为b64 str后再判断前缀
            if strToBase64(line).startswith('G1swbRtbMzJtRG93bmxvYWQbWzBtIGh0dHBzOi8vZGVuby5sYW5kL3'):
                continue
            error_msg += f"{line}\n"

    if error_msg:
        cron_logger.error(f'user_db_id:{user_id} deno cli error,result:\n{error_msg}')
    elif res:
        # success
        cron_logger.info(f'user_db_id:{user_id} deno cli success,result:\n{res}')

        for line in res.split('\n'):
            line = line.strip()
            if not line:
                continue
            if 'exported to https://stat.ink' in line:
                if 'salmon3' in line:
                    coop_cnt += 1
                else:
                    battle_cnt += 1
                url = line.split('to ')[1].split('spl3')[0].split('salmon3')[0][:-1]

    cron_logger.info(f'user_db_id:{user_id} result: {battle_cnt}, {coop_cnt}, {url}')
    return battle_cnt, coop_cnt, url, error_msg


def strToBase64(s):
    '''
    将字符串转换为base64字符串
    :param s:
    :return:
    '''
    strEncode = base64.b64encode(s.encode('utf8'))
    return str(strEncode, encoding='utf8')
