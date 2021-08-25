from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class InactivityPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.inactivity.permissions[self.name]

    read = auto()
    write = auto()
    scan = auto()
