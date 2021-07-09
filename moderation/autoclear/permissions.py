from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class AutoClearPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.autoclear.permissions[self.name]

    read = auto()
    write = auto()
