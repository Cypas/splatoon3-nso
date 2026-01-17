from nonebot import logger
from redis import asyncio as aioredis  # noqa
import redis
from typing import Dict, Tuple, List

from ..config import plugin_config

from redis import asyncio as aioredis  # noqa（保留原有导入，避免影响其他逻辑）
import redis
from typing import Dict, Tuple, Optional, Any
from abc import ABC, abstractmethod

from ..config import plugin_config


class BaseRedisManager(ABC):
    """Redis 管理基类（抽象公共逻辑）"""
    _pool_dict: Dict[Tuple[str, int, int, str], redis.ConnectionPool] = {}
    # 每个子类的默认配置（由子类重写）
    DEFAULT_DB: int = 0
    DEFAULT_EXPIRE: int = 0

    def __init__(
            self,
            host: str = plugin_config.splatoon3_redis_ip,
            port: int = plugin_config.splatoon3_redis_port,
            db: Optional[int] = None,
            password: str = plugin_config.splatoon3_redis_psw,
            decode_responses: bool = True,
            max_connections: int = 50
    ) -> None:
        # 使用子类的默认DB（如果未传参）
        db = db or self.DEFAULT_DB
        pool_key = (host, port, db, password)

        # 单例连接池（避免重复创建）
        if pool_key not in self._pool_dict:
            self._pool_dict[pool_key] = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses,
                max_connections=max_connections,
            )

        self._r = redis.Redis(connection_pool=self._pool_dict[pool_key])
        self._ping()

    def _ping(self) -> None:
        """检测Redis连接，失败则抛异常"""
        try:
            self._r.ping()
        except Exception as e:  # 替换BaseException为更具体的Exception
            raise ConnectionError(f"Redis连接失败: {str(e)}") from e

    def get_redis(self) -> redis.Redis:
        """获取Redis客户端实例"""
        return self._r

    # 基础通用方法
    def get(self, key: str) -> Optional[str]:
        """获取字符串值"""
        return self.get_redis().get(key)

    def set(self, key: str, value: str, expire: Optional[int] = None) -> None:
        """设置字符串值（带过期时间）"""
        expire = expire or self.DEFAULT_EXPIRE
        self.get_redis().set(key, value, expire)

    def delete(self, key: str) -> None:
        """删除指定key"""
        self.get_redis().delete(key)

    def hset(self, key: str, mapping: Dict[str, Any]) -> None:
        """批量设置hash字段"""
        self.get_redis().hset(key, mapping=mapping)

    def hget_all(self, key: str) -> Dict[str, Any]:
        """获取hash所有字段"""
        return self.get_redis().hgetall(key)


class RedisManagerGToken(BaseRedisManager):
    """GToken专用Redis管理器（DB=3）"""
    DEFAULT_DB = 3
    DEFAULT_EXPIRE = 60 * 60 * 3 - 5 * 60  # 2小时55分钟（原gtoken过期时间）


class RedisManagerGetlc(BaseRedisManager):
    """LoginCode专用Redis管理器（DB=2，扩展hash方法）"""
    DEFAULT_DB = 2


# 全局实例（保持原有调用方式不变）
try:
    rm_gtoken = RedisManagerGToken()
    rm_lc = RedisManagerGetlc()
except Exception as e:
    logger.error("redis连接失败，请检查redis连接参数")
    rm_gtoken = None
    rm_lc = None

# --------------------------
# 原有异步函数（保持兼容）
# --------------------------
async def rget_gtoken(sp_id: str) -> Optional[str]:
    """redis get gtoken"""
    return rm_gtoken.get(sp_id)


async def rset_gtoken(sp_id: str, g_token: str) -> None:
    """redis set gtoken（使用默认过期时间）"""
    rm_gtoken.set(sp_id, g_token)


async def rget_lc(login_code: str) -> Dict[str, Any]:
    """redis hget_all login_info"""
    return rm_lc.hget_all(login_code)


async def rset_lc(login_code: str, mapping: Dict[str, Any]) -> None:
    """redis hset login_info"""
    rm_lc.hset(login_code, mapping)


async def rdel_lc(login_code: str) -> None:
    """redis del login_code"""
    rm_lc.delete(login_code)
