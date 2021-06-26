from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class AutoDeleteMessagesPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.auto_delete_messages.permissions[self.name]

    read = auto()
    write = auto()
