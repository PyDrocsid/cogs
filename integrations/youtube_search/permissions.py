from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class YouTubePermission(BasePermission):
    @property
    def description(self) -> str:
        return t.reddit.permissions[self.name]

    read = auto()
    write = auto()
