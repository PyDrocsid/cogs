from __future__ import annotations

from typing import Union, Optional
from uuid import uuid4

from sqlalchemy import Column, Text, Boolean, BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from PyDrocsid.database import db, Base
from PyDrocsid.permission import BasePermissionLevel


class CustomCommand(Base):
    __tablename__ = "custom_command"

    id: Union[Column, str] = Column(String(36), primary_key=True, unique=True)
    name: Union[Column, str] = Column(Text, unique=True)
    description: Union[Column, str] = Column(Text)
    disabled: Union[Column, bool] = Column(Boolean)
    channel_parameter: Union[Column, bool] = Column(Boolean)
    channel_id: Union[Column, Optional[int]] = Column(BigInteger, nullable=True)
    delete_command: Union[Column, bool] = Column(Boolean)
    permission_level: Union[Column, bool] = Column(Integer)
    requires_confirmation: Union[Column, bool] = Column(Boolean)
    user_parameter: Union[Column, bool] = Column(Boolean)
    data: Union[Column, str] = Column(Text)
    aliases: list[Alias] = relationship(
        "Alias",
        back_populates="command",
        cascade="all, delete",
        order_by="Alias.name",
    )

    @staticmethod
    async def create(name: str, data: str, disabled: bool, permission_level: BasePermissionLevel) -> CustomCommand:
        row = CustomCommand(
            id=str(uuid4()),
            name=name,
            description=None,
            disabled=disabled,
            channel_parameter=False,
            channel_id=None,
            delete_command=False,
            permission_level=permission_level.level,
            requires_confirmation=False,
            user_parameter=True,
            data=data,
        )
        await db.add(row)
        return row

    @property
    def alias_names(self) -> list[str]:
        return [alias.name for alias in self.aliases]

    async def add_alias(self, name: str) -> Alias:
        alias = Alias(id=str(uuid4()), name=name, command_id=self.id)
        self.aliases.append(alias)
        await db.add(alias)
        return alias


class Alias(Base):
    __tablename__ = "custom_command_alias"

    id: Union[Column, str] = Column(String(36), primary_key=True, unique=True)
    name: Union[Column, str] = Column(Text, unique=True)
    command_id: Union[Column, str] = Column(String(36), ForeignKey("custom_command.id"))
    command: CustomCommand = relationship("CustomCommand", back_populates="aliases")
