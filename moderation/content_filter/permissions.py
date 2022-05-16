from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class ContentFilterPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.content_filter.permissions[self.name]

    bypass = auto()
    read = auto()
    write = auto()
