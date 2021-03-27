from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class AutoModPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.automod.permissions[self.name]

    autokick_read = auto()
    autokick_write = auto()
    instantkick_read = auto()
    instantkick_write = auto()
