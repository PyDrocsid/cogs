from enum import auto

from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t


class UserInfoPermission(BasePermission):
    @property
    def description(self) -> str:
        return t.user_info.permissions[self.name]

    view_userinfo = auto()
    view_userlog = auto()
    init_join_log = auto()
