from PyDrocsid.settings import Settings


class AntiRaidSettings(Settings):
    timespan = 1
    threshold = 3
    alert_cooldown = 10
    keep_alerts = 60
    alert_channel = -1
