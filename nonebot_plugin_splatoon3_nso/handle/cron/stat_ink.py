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
from ...s3s.splatoon import Splatoon
from ...utils import proxy_address, convert_td
from ...utils.utils import DIR_RESOURCE, init_path, get_msg_id
from ...data.data_source import model_get_all_stat_user, dict_clear_user_info_dict, global_user_info_dict, \
    dict_get_or_set_user_info, model_get_or_set_user
from ..send_msg import notify_to_private, report_notify_to_channel, cron_notify_to_channel
from .utils import user_remove_duplicates, cron_logger
from ...utils.bot import Kook_ActionFailed

# 错误对局，没有会员，nso被ban，无效登录凭证
expected_str_list = ["status: 500", "Membership required", "has be banned", "invalid_grant"]


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

    complete_cnt, upload_cnt, error_cnt, else_error_cnt, notice_error_cnt, battle_error_cnt, membership_error_cnt, invalid_grant_error_cnt = 0, 0, 0, 0, 0, 0, 0, 0
    _pool = 40
    for i in range(0, len(db_users), _pool):
        pool_users_list = db_users[i:i + _pool]
        tasks = [sync_stat_ink_func(db_user) for db_user in pool_users_list]
        res = await asyncio.gather(*tasks)
        for r in res:
            is_complete, is_upload, is_error, is_notice_error, is_else_error, is_battle_error, is_membership_error, is_invalid_grant = r
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
            if is_battle_error:
                battle_error_cnt += 1
            if is_membership_error:
                membership_error_cnt += 1
            if is_invalid_grant:
                invalid_grant_error_cnt += 1
    # 耗时
    str_time = convert_td(dt.utcnow() - t)
    cron_msg = (f"sync_stat_ink end: {str_time}\n"
                f"complete_cnt: {complete_cnt}, upload_cnt: {upload_cnt}\n"
                f"error_cnt: {error_cnt},battle_error_cnt: {battle_error_cnt},membership_error_cnt: {membership_error_cnt},invalid_grant_error_cnt:{invalid_grant_error_cnt},notice_error_cnt: {notice_error_cnt}")
    cron_logger.info(cron_msg)
    notice_msg = (f"耗时:{str_time}\n完成: {complete_cnt},同步: {upload_cnt}\n"
                  f"错误: {error_cnt},对战错误: {battle_error_cnt},缺少会员: {membership_error_cnt},无效登录吗?: {invalid_grant_error_cnt}\n"
                  f"通知错误: {notice_error_cnt}")

    await cron_notify_to_channel("sync_stat_ink", "end", notice_msg)


async def sync_stat_ink_func(db_user: UserTable):
    """同步stat.ink"""
    is_complete, is_upload, is_error, is_else_error, is_notice_error, is_battle_error, is_membership_error, is_invalid_grant = False, False, False, False, False, False, False, False

    cron_logger.debug(f"get user: {db_user.user_name}, have stat_key: {db_user.stat_key}")

    res = await get_post_stat_msg(db_user)
    if not isinstance(res, tuple):
        is_else_error = True
        return is_complete, is_upload, is_error, is_notice_error, is_else_error, is_battle_error, is_membership_error, is_invalid_grant

    msg, error_msg = res

    platform = db_user.platform
    user_id = db_user.user_id
    msg_id = get_msg_id(platform, user_id)
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
            except Kook_ActionFailed as e:
                if e.status_code == 40000:
                    if e.message.startswith("你已被对方屏蔽"):
                        dict_get_or_set_user_info(platform, user_id, stat_notify=0, report_notify=0)
                        cron_logger.warning(
                            f'sync_stat_ink send private error:db_user_id:{db_user.id}，mgs_id:{msg_id},error:用户已屏蔽发信bot，已关闭其通知权限')
                is_notice_error = True
            except Exception as e:
                cron_logger.error(
                    f"sync_stat_ink send private error:db_user_id:{db_user.id}，mgs_id:{msg_id},error: {e}")
                is_notice_error = True

    if error_msg:
        is_error = True
        if "status: 500" in error_msg:
            is_battle_error = True
        if "Membership required" in error_msg:
            is_membership_error = True
        if "invalid_grant" in error_msg:
            is_invalid_grant = True

    return is_complete, is_upload, is_error, is_notice_error, is_else_error, is_battle_error, is_membership_error, is_invalid_grant


async def get_post_stat_msg(db_user):
    """获取同步消息文本"""
    cron_logger.debug(f"get user: {db_user.user_name}, have stat_key: {db_user.stat_key}")
    if not (db_user and db_user.session_token and db_user.stat_key):
        return
    # User复用以及定时任务用user对象
    platform = db_user.platform
    user_id = db_user.user_id
    msg_id = get_msg_id(platform, user_id)
    global_user_info = global_user_info_dict.get(msg_id)
    if global_user_info:
        u = global_user_info
    else:
        # 新建cron任务对象
        u = dict_get_or_set_user_info(platform, user_id)
        if not u or not u.session_token:
            return
        splatoon = Splatoon(None, None, u)
        try:
            # 刷新token
            await splatoon.refresh_gtoken_and_bullettoken()
        except ValueError as e:
            if 'invalid_grant' in str(e) or 'Membership required' in str(e) or "has be banned" in str(e):
                # 无效登录或会员过期 或被封禁
                # 关闭连接池
                await splatoon.req_client.close()
                return "", str(e)
        except Exception as e:
            cron_logger.error(f'stat_ink_task error: {msg_id},refresh_gtoken_and_bullettoken error:{e}')
            return "", str(e)
        finally:
            # 关闭连接池
            await splatoon.req_client.close()

    # 两个f_api 负载均衡
    f_url_lst = [F_GEN_URL, F_GEN_URL_2]
    random.shuffle(f_url_lst)
    f_gen_url = f_url_lst[0]
    res = exported_to_stat_ink(db_user.id, u.session_token, db_user.stat_key, f_gen_url, g_token=u.g_token,
                               bullet_token=u.bullet_token)

    if not isinstance(res, tuple):
        return
    battle_cnt, coop_cnt, url, error_msg = res

    flag_need_retry = True
    # f-api重试
    if error_msg:
        # 排除预期错误
        for expected_str in expected_str_list:
            if expected_str in error_msg:
                flag_need_retry = False
        if flag_need_retry:
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
            res = exported_to_stat_ink(db_user.id, u.session_token, db_user.stat_key, next_f_url,
                                       g_token=u.g_token,
                                       bullet_token=u.bullet_token)

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
        cmd = f"git clone https://github.com/Cypas/s3si.ts {s3s_folder}"
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

    env = {}
    # deno代理配置
    # http
    if proxy_address:
        env.update({"HTTP_PROXY": f"http://{proxy_address}",
                    "HTTPS_PROXY": f"http://{proxy_address}"
                    })
    # no proxy
    if plugin_config.splatoon3_proxy_list_mode and proxy_address:
        env.update({"NO_PROXY": f"api.lp1.av5ja.srv.nintendo.net"})

    # run deno
    cmd = f'{deno_path} run -Ar ./s3si.ts -n -p {path_config_file}'
    cron_logger.debug(cmd)

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
        if "html" in e:
            e = "html error"
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
        expect = ""
        for expected_str in expected_str_list:
            if expected_str in error_msg:
                expect = expected_str
                break
        if expect:
            cron_logger.error(f'user_db_id:{user_id} deno cli error,result: {expect}')
        else:
            cron_logger.error(f'user_db_id:{user_id} deno cli unexpected error,result:\n{error_msg}')
    elif res:
        # success
        cron_logger.debug(f'user_db_id:{user_id} deno cli success,result:\n{res}')

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
