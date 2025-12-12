import asyncio

from nonebot_plugin_splatoon3_nso.s3s.iksm import S3S

async def run_s3s():
    s3s = S3S(platform="cc", user_id="123")
    # s3s.get_nsoapp_version()
    session_token = "eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLm5pbnRlbmRvLmNvbSIsImV4cCI6MTgwOTY2MTkyMiwidHlwIjoic2Vzc2lvbl90b2tlbiIsImF1ZCI6IjcxYjk2M2MxYjdiNmQxMTkiLCJqdGkiOjE3NDcxODA5MjgwLCJzdDpzY3AiOlswLDgsOSwxNywyM10sImlhdCI6MTc0NjU4OTkyMiwic3ViIjoiZTI0MzdlZDlkODcxMjdlYyJ9.mLtScCHt1ewR6yrpbx4ISRm6JOCFaidLSgDTbnLvEbI"
    await s3s.get_gtoken(session_token)



if __name__ == "__main__":
    asyncio.run(run_s3s())