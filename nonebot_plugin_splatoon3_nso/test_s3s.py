import asyncio

from nonebot_plugin_splatoon3_nso.s3s.iksm import S3S

async def run_s3s():
    s3s = S3S(platform="cc", user_id="123")
    # s3s.get_nsoapp_version()
    session_token = ""
    await s3s.get_gtoken(session_token)



if __name__ == "__main__":
    asyncio.run(run_s3s())