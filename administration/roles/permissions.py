from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class RolesPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.roles.permissions[self.name]

    config_read = auto()
    config_write = auto()
    auth_read = auto()
    auth_write = auto()
    list_members = auto()
    roles_clone = auto()
