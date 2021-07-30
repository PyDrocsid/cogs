from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class AutoReactionPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.auto_reaction.permissions[self.name]

    read = auto()
    write = auto()
