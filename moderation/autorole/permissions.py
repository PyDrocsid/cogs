from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class AutoRolePermission(BasePermission):
    @property
    def description(self) -> str:
        return t.autorole.permissions[self.name]

    read = auto()
    write = auto()
