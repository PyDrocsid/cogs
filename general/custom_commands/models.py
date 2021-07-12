from __future__ import annotations

from typing import Union, Optional

from sqlalchemy import Column, Text, Boolean, BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from PyDrocsid.database import db


class CustomCommand(db.Base):
    __tablename__ = "custom_command"

    id: Union[Column, str] = Column(String(36), primary_key=True, unique=True)
    name: Union[Column, str] = Column(Text(collation="utf8mb4_bin"), unique=True)
    description: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    disabled: Union[Column, bool] = Column(Boolean)
    channel_parameter: Union[Column, bool] = Column(Boolean)
    channel_id: Union[Column, Optional[int]] = Column(BigInteger, nullable=True)
    delete_command: Union[Column, bool] = Column(Boolean)
    permission_level: Union[Column, bool] = Column(Integer)
    requires_confirmation: Union[Column, bool] = Column(Boolean)
    data: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    aliases: list[Alias] = relationship("Alias", back_populates="command", cascade="all, delete")


class Alias(db.Base):
    __tablename__ = "custom_command_alias"

    id: Union[Column, str] = Column(String(36), primary_key=True, unique=True)
    name: Union[Column, str] = Column(Text(collation="utf8mb4_bin"), unique=True)
    command_id: Union[Column, str] = Column(String(36), ForeignKey("custom_command.id"))
    command: CustomCommand = relationship("CustomCommand", back_populates="aliases")
