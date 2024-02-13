import asyncio
import datetime
import os
import json
import subprocess


from ...data.db_sqlite import UserTable
from ...config import plugin_config
from ...utils import proxy_address
from ...utils.utils import DIR_RESOURCE, init_path
from ...data.data_source import model_get_all_stat_user
from ..send_msg import notify_to_private, report_notify_to_channel, cron_notify_to_channel
from .utils import user_remove_duplicates, cron_logger


async def sync_stat_ink():
    """同步至stat"""
    cron_msg = f"sync_stat_ink start"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel(cron_msg)
    t = datetime.datetime.utcnow()

    db_users = model_get_all_stat_user()
    # 去重
    db_users = user_remove_duplicates(db_users)

    _pool = 4
    for i in range(0, len(db_users), _pool):
        pool_users_list = db_users[i:i + _pool]
        tasks = [sync_stat_ink_func(db_user) for db_user in pool_users_list]
        res = await asyncio.gather(*tasks)

    cron_msg = f"sync_stat_ink end: {datetime.datetime.utcnow() - t}"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel(cron_msg)


async def sync_stat_ink_func(db_user: UserTable):
    """同步stat.ink"""

    cron_logger.debug(f"get user: {db_user.user_name}, have stat_key: {db_user.stat_key}")

    msg = get_post_stat_msg(db_user)

    if msg and db_user.stat_notify:
        cron_logger.debug(f"{db_user.id}, {db_user.user_name}, {msg}")
        # 通知到频道
        await report_notify_to_channel(db_user.platform, db_user.user_id, msg, _type="job")
        # 通知到私信
        msg += "\n/stat_notify close 关闭stat.ink同步情况推送"
        await notify_to_private(db_user.platform, db_user.user_id, msg)


def get_post_stat_msg(db_user):
    """获取同步消息文本"""

    cron_logger.debug(f"get user: {db_user.user_name}, have stat_key: {db_user.stat_key}")
    if not (db_user and db_user.session_token and db_user.stat_key):
        return

    res = exported_to_stat_ink(db_user.id, db_user.session_token, db_user.stat_key, g_token=db_user.g_token,
                               bullet_token=db_user.bullet_token)

    if not res:
        return

    battle_cnt, coop_cnt, url = res
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

    return msg


async def update_s3si_ts():
    # 更新 s3si_ts 上传脚本
    cron_msg = f"update_s3si_ts start"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel(cron_msg)
    t = datetime.datetime.utcnow()

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

    cron_msg = f"update_s3si_ts end, {(datetime.datetime.utcnow() - t).seconds}s"
    cron_logger.info(cron_msg)
    await cron_notify_to_channel(cron_msg)


def exported_to_stat_ink(user_id, session_token, api_key, user_lang="zh-CN", g_token="", bullet_token=""):
    """同步战绩文件至stat.ink"""
    cron_logger.info(f'exported_to_stat_ink: {user_id}')
    cron_logger.debug(f'session_token: {session_token}')
    cron_logger.debug(f'api_key: {api_key}')
    user_lang = user_lang or 'zh-CN'

    s3sits_folder = f'{DIR_RESOURCE}/s3sits_git'
    os.chdir(s3sits_folder)

    path_config_file = f'{s3sits_folder}/user_configs/config_{user_id}.json'
    if not os.path.exists(path_config_file):
        # 新建文件
        config_data = {
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
        cmds = [
            f"""sed -i 's/userLang[^,]*,/userLang\": \"{user_lang}\",/' {path_config_file}""",
            f"""sed -i 's/sessionToken[^,]*,/sessionToken\": \"{session_token}\",/' {path_config_file}""",
            f"""sed -i 's/statInkApiKey[^,]*,/statInkApiKey\": \"{api_key}\",/' {path_config_file}""",
        ]
        if g_token and bullet_token:
            cmds.append(f"""sed -i 's/gToken[^,]*,/gToken\": \"{g_token}\",/' {path_config_file}""")
            cmds.append(f"""sed -i 's/bulletToken[^,]*,/bulletToken\": \"{bullet_token}\",/' {path_config_file}""")

        for cmd in cmds:
            cron_logger.debug(f'cli: {cmd}')
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
        env.update({"NO_PROXY": f"stat.ink"})

    # run deno
    deno_path = plugin_config.splatoon3_deno_path
    if not deno_path or not os.path.exists(deno_path):
        cron_logger.info(f'deno_path not set: {deno_path or ""} '.center(120, '-'))
        return

    cmd = f'{deno_path} run -Ar ./s3si.ts -n -p {path_config_file}'
    cron_logger.info(cmd)
    rtn = subprocess.run(cmd.split(' '), stdout=subprocess.PIPE, env=env).stdout.decode('utf-8')
    cron_logger.info(f'{user_id} cli: {rtn}')

    battle_cnt = 0
    coop_cnt = 0
    url = ''
    for line in rtn.split('\n'):
        line = line.strip()
        if not line:
            continue
        if 'exported to https://stat.ink' in line:
            if 'salmon3' in line:
                coop_cnt += 1
            else:
                battle_cnt += 1
            url = line.split('to ')[1].split('spl3')[0].split('salmon3')[0][:-1]

    cron_logger.info(f'{user_id} result: {battle_cnt}, {coop_cnt}, {url}')
    if battle_cnt or coop_cnt:
        return battle_cnt, coop_cnt, url
