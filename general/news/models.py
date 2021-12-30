from typing import Union, Optional

from PyDrocsid.database import db, Base
from sqlalchemy import Column, BigInteger


class NewsAuthorization(Base):
    __tablename__ = "news_authorization"

    user_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    channel_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    notification_role_id: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(user_id: int, channel_id: int, notification_role_id: Optional[int]) -> "NewsAuthorization":
        row = NewsAuthorization(user_id=user_id, channel_id=channel_id, notification_role_id=notification_role_id)
        await db.add(row)
        return row
