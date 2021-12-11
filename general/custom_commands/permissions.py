from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class CustomCommandsPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.custom_commands.permissions[self.name]

    read = auto()
    write = auto()
