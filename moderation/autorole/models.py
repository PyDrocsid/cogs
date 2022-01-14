from typing import Union

from sqlalchemy import Column, BigInteger

from PyDrocsid.async_thread import LockDeco
from PyDrocsid.database import db, select, delete, Base
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis


@LockDeco
async def load_cache():
    if await redis.exists(load_key := "autorole_loaded"):
        return

    roles = [row.role_id async for row in await db.stream(select(AutoRole))]

    async with redis.pipeline() as pipe:
        await pipe.delete(role_key := "autorole_roles")
        if roles:
            await pipe.sadd(role_key, *roles)
            await pipe.expire(role_key, CACHE_TTL)
        await pipe.setex(load_key, CACHE_TTL, 1)
        await pipe.execute()


class AutoRole(Base):
    __tablename__ = "autorole"

    role_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def add(role: int):
        await load_cache()
        await redis.sadd(key := "autorole_roles", role)
        await redis.expire(key, CACHE_TTL)
        await db.add(AutoRole(role_id=role))

    @staticmethod
    async def exists(role: int) -> bool:
        await load_cache()
        return await redis.sismember("autorole_roles", role)

    @staticmethod
    async def all() -> list[int]:
        await load_cache()
        return list(map(int, await redis.smembers("autorole_roles")))

    @staticmethod
    async def remove(role: int):
        await load_cache()
        await redis.srem(key := "autorole_roles", role)
        await redis.expire(key, CACHE_TTL)
        await db.exec(delete(AutoRole).filter_by(role_id=role))
