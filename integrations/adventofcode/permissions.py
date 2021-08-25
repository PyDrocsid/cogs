from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class AdventOfCodePermission(BasePermission):
    @property
    def description(self) -> str:
        return t.adventofcode.permissions[self.name]

    clear = auto()
    link_read = auto()
    link_write = auto()
    role_read = auto()
    role_write = auto()
