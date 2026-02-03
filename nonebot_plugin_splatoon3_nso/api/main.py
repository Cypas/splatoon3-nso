import os
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.responses import FileResponse, Response
from nonebot import logger
from fastapi.middleware.cors import CORSMiddleware

from ..utils.utils import DIR_RESOURCE
from ..utils.redis import api_rget_json_file_name

fast_logger = logger.bind(fastapi=True)
app = FastAPI(
    title="小鱿鱿外部fastapi接口",
    version="1.0.0",
    description="供外部调用小鱿鱿nso函数"
)

origins = [
    "https://blog.ayano.top",
    "http://blog.ayano.top",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# plugins/my_calc/api/main.py 核心接口片段
@app.get("/nso/seedchecker")
async def download_seed_checker(secret_code: str = Query(..., min_length=1, max_length=24)):
    """
    使用小鱿鱿创建的密钥下载观星json文件
    """
    try:
        if len(secret_code) != 24:
            return {
                "code": 403,
                "msg": "观星访问密钥错误,长度应为24位，请用小鱿鱿重新生成"
            }
        # 取真实redis key
        real_secret_code = secret_code.replace("xyy-seedchecker-","")
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
        # 正常返回文件流
        return FileResponse(
            path=file_path,
            filename=file_name,  # 下载时的文件名
            media_type="application/json"  # json类型
        )

    except Exception as e:
        fast_logger.error(f"[fastapi]观星下载 error:{e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误")
