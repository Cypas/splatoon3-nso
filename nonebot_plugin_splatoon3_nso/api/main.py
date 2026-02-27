import os
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.responses import FileResponse, Response
from nonebot import logger
from fastapi.middleware.cors import CORSMiddleware

from ..utils.utils import DIR_RESOURCE, get_jwt_exp_info
from ..utils.redis import api_rget_json_file_name, api_rdel_json_file_name, api_rget_info

fast_logger = logger.bind(fastapi=True)
app = FastAPI(
    title="小鱿鱿外部fastapi接口",
    version="1.0.0",
    description="供外部调用小鱿鱿nso函数"
)

origins = [
    "https://blog.ayano.top",
    "http://blog.ayano.top",
    "https://api.lp1.av5ja.srv.nintendo.net"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,
)

# plugins/my_calc/api/main.py 核心接口片段
@app.get("/nso/seedchecker")
async def download_seed_checker(secret_code: str = Query(..., min_length=1, max_length=40)):
    """
    使用小鱿鱿创建的密钥下载观星json文件
    """
    try:
        if secret_code.startswith("xyy-nsoweb-"):
            return {
                "code": 403,
                "msg": "你输入的是nso网页版的访问密钥，这里需要输入的是 观星访问密钥，观星密钥应为xyy-seedchecker- 开头，你是不是复制错了呢?"
            }
        if len(secret_code) != 24:
            return {
                "code": 403,
                "msg": "观星访问密钥错误,长度应为24位，请用小鱿鱿重新生成"
            }
        # 取真实redis key
        real_secret_code = secret_code.replace("xyy-seedchecker-", "")
        file_name = await api_rget_json_file_name(real_secret_code)
        if not file_name:
            return {
                "code": 403,
                "msg": "观星访问密钥错误或已过期，请用小鱿鱿重新生成"
            }
        # 读取观星json文件
        file_dir = os.path.join(DIR_RESOURCE, "temp_seedchecker_file")
        file_path = os.path.join(file_dir, file_name)
        # 判断文件是否存在
        if not os.path.exists(file_path):
            return {
                "code": 404,
                "msg": "观星文件不存在，请用小鱿鱿重新生成"
            }
        await api_rdel_json_file_name(real_secret_code)
        # 正常返回文件流
        return FileResponse(
            path=file_path,
            filename=file_name,  # 下载时的文件名
            media_type="application/octet-stream"  # 二进制流类型
        )

    except Exception as e:
        fast_logger.error(f"[fastapi]观星下载 error:{e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误")


@app.get("/nso/nso_web/login")
async def nso_web_login(secret_code: str = Query(..., min_length=1, max_length=40)):
    """
    获取小鱿鱿创建的密钥gtoken
    """
    try:
        if secret_code.startswith("xyy-seedchecker-"):
            return {
                "code": 403,
                "msg": "你输入的是观星访问密钥，这里需要输入的是 nso网页版访问密钥，nso网页版访问密钥应为xyy-nsoweb- 开头，你是不是复制错了呢?"
            }
        if len(secret_code) != 19:
            return {
                "code": 403,
                "msg": "nso网页版访问密钥错误,长度应为19位，请用小鱿鱿重新生成"
            }
        # 取真实redis key
        real_secret_code = secret_code.replace("xyy-nsoweb-", "")
        user_info = await api_rget_info(real_secret_code)
        if not user_info:
            return {
                "code": 403,
                "msg": "nso网页版访问密钥错误或已过期，请用小鱿鱿重新生成"
            }
        # 读取gtoken
        gtoken = user_info.get("gtoken")
        # 校验gtoken并计算剩余时间
        jwt_info = get_jwt_exp_info(gtoken)
        remaining_seconds = jwt_info.get("remaining_seconds")
        exp_ts = jwt_info.get("exp_ts")
        exp_date = jwt_info.get("exp_date")
        if remaining_seconds <= 0:
            return {
                "code": 403,
                "msg": "密钥已过期，请用小鱿鱿重新生成"
            }
        else:
            return {
                "code": 0,
                "msg": "gtoken获取成功",
                "data": {
                    "gtoken": gtoken,
                    "remaining_seconds": remaining_seconds,
                    "exp_ts": exp_ts,
                    "exp_date": exp_date
                }
            }

    except Exception as e:
        fast_logger.error(f"[fastapi]鱿鱼圈访问 error:{e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误")
