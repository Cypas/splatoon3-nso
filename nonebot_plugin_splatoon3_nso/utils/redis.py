from redis import asyncio as aioredis  # noqa
import redis
from typing import Dict, Tuple, List

from ..config import plugin_config


class RedisManagerGToken(object):
    _pool_dict: Dict[Tuple[str, int, int, str], redis.ConnectionPool] = {}

    def __init__(
            self,
            host: str = plugin_config.splatoon3_redis_ip,
            port: int = plugin_config.splatoon3_redis_port,
            db: int = 3,
            password: str = plugin_config.splatoon3_redis_psw,
            decode_responses: bool = True,
            max_connections: int = 50
    ) -> None:
        pool_key = (host, port, db, password)
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

    def get_redis(self) -> redis.Redis:
        return self._r

    def _ping(self):
        try:
            self._r.ping()
        except BaseException as e:
            raise e

    def get(self, key: str) -> str:
        value = self.get_redis().get(key)
        return value

    def set(self, key: str, value: str, expire: int) -> None:
        self.get_redis().set(key, value, expire)

    def delete(self, key: str) -> None:
        self.get_redis().delete(key)


class RedisManagerGetlc(object):
    _pool_dict: Dict[Tuple[str, int, int, str], redis.ConnectionPool] = {}

    def __init__(
            self,
            host: str = plugin_config.splatoon3_redis_ip,
            port: int = plugin_config.splatoon3_redis_port,
            db: int = 2,
            password: str = plugin_config.splatoon3_redis_psw,
            decode_responses: bool = True,
            max_connections: int = 50
    ) -> None:
        pool_key = (host, port, db, password)
        if pool_key not in self._pool_dict:
            self._pool_dict[pool_key] = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses,
                max_connections=max_connections
            )
        self._r = redis.Redis(connection_pool=self._pool_dict[pool_key])
        self._ping()

    def get_redis(self) -> redis.Redis:
        return self._r

    def _ping(self):
        try:
            self._r.ping()
        except BaseException as e:
            raise e

    def get(self, key: str) -> str:
        value = self.get_redis().get(key)
        return value

    def set(self, key: str, value: str, expire: int) -> None:
        self.get_redis().set(key, value, expire)

    def delete(self, key: str) -> None:
        self.get_redis().delete(key)

    def hset(self, key: str, mapping: dict) -> None:
        self.get_redis().hset(key, mapping=mapping)

    def hget_all(self, key: str) -> Dict:
        mapping = self.get_redis().hgetall(key)
        return mapping


rm_gtoken = RedisManagerGToken()
rm_lc = RedisManagerGetlc()


async def rget_gtoken(sp_id) -> str | None:
    """redis get gtoken"""
    return rm_gtoken.get(sp_id)


async def rset_gtoken(sp_id: str, g_token: str) -> None:
    """redis set gtoken"""
    rm_gtoken.set(sp_id, g_token, expire=(60 * 60 * 3 - 5 * 60))


async def rget_lc(login_code: str) -> dict:
    """redis hget_all login_info"""
    mapping = rm_lc.hget_all(login_code)
    return mapping


async def rset_lc(login_code: str, mapping: Dict) -> None:
    """redis hset login_info"""
    rm_lc.hset(login_code, mapping)


async def rdel_lc(login_code: str) -> None:
    """redis del login_code"""
    rm_lc.delete(login_code)
