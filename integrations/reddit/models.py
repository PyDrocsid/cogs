from __future__ import annotations

from datetime import datetime, timedelta
from typing import Union

from sqlalchemy import Column, String, BigInteger, DateTime

from PyDrocsid.database import db, delete, filter_by


class RedditChannel(db.Base):
    __tablename__ = "reddit_channel"

    subreddit: Union[Column, str] = Column(String(32), primary_key=True)
    channel: Union[Column, int] = Column(BigInteger, primary_key=True)
    guild_id: Union[Column, int] = Column(BigInteger, primary_key=True)

    @staticmethod
    async def create(subreddit: str, channel: int, guild_id: int) -> RedditChannel:
        row = RedditChannel(subreddit=subreddit, channel=channel, guild_id=guild_id)
        await db.add(row)
        return row


class RedditPost(db.Base):
    __tablename__ = "reddit_post"

    post_id: Union[Column, str] = Column(String(16), primary_key=True)
    timestamp: Union[Column, datetime] = Column(DateTime)
    guild_id: Union[Column, int] = Column(BigInteger, primary_key=True)

    @staticmethod
    async def create(post_id: str, guild_id: int) -> RedditPost:
        row = RedditPost(post_id=post_id, timestamp=datetime.utcnow(), guild_id=guild_id)
        await db.add(row)
        return row

    @staticmethod
    async def clean():
        drop_before_timestamp = datetime.utcnow() - timedelta(weeks=1)
        await db.exec(delete(RedditPost).filter(RedditPost.timestamp < drop_before_timestamp))

    @staticmethod
    async def post(guild_id: int, post_id: str) -> bool:
        if await db.exists(filter_by(RedditPost, post_id=post_id, guild_id=guild_id)):
            return False

        await RedditPost.create(post_id, guild_id)
        return True
