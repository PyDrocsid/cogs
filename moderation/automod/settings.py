from PyDrocsid.settings import Settings


class AutoKickMode:
    off = 0
    normal = 1
    reverse = 2


class AutoModSettings(Settings):
    autokick_mode = AutoKickMode.off
    autokick_delay = 30
    autokick_role = -1
    instantkick_role = -1
