from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class RoleNotificationsPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.role_notifications.permissions[self.name]

    read = auto()
    write = auto()
