from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class ModPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.mod.permissions[self.name]

    warn = auto()
    mute = auto()
    kick = auto()
    ban = auto()
    modtools_write = auto()
