from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class AntiRaidPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.antiraid.permissions[self.name]

    read = auto()
    timekick = auto()
    joinkick = auto()
