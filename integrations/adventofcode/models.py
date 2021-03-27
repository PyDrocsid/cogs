from typing import Union

from PyDrocsid.database import db
from sqlalchemy import Column, BigInteger, Text


class AOCLink(db.Base):
    __tablename__ = "aoc_link"

    discord_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)
    aoc_id: Union[Column, str] = Column(Text, unique=True)
    solutions: Union[Column, str] = Column(Text(collation="utf8mb4_bin"), nullable=True)

    @staticmethod
    async def create(discord_id: int, aoc_id: str) -> "AOCLink":
        link = AOCLink(discord_id=discord_id, aoc_id=aoc_id)
        await db.add(link)
        return link

    @staticmethod
    async def publish(discord_id: int, url: str):
        row = await db.get(AOCLink, discord_id=discord_id)
        row.solutions = url

    @staticmethod
    async def unpublish(discord_id: int):
        row = await db.get(AOCLink, discord_id=discord_id)
        row.solutions = None
