from PyDrocsid.settings import Settings


class SpamDetectionSettings(Settings):
    max_hops_alert = 0
    max_hops_warning = 0
    max_hops_temp_mute = 0
    temp_mute_duration = 10
