from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class ThreadsPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.threads.permissions[self.name]

    list = auto()
