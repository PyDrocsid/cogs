from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class UserNotePermissions(BasePermission):
    @property
    def description(self) -> str:
        return t.user_notes.permissions[self.name]

    read = auto()
    write = auto()
