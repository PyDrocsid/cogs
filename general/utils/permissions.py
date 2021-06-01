from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class UtilsPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.utils.permissions[self.name]

    suggest_role_color = auto()
