from PyDrocsid.settings import Settings


class LoggingSettings(Settings):
    maxage = -1
    edit_mindiff = 1

    edit_channel = -1
    delete_channel = -1
    alert_channel = -1
    changelog_channel = -1
