from PyDrocsid.settings import Settings


class PollsDefaultSettings(Settings):
    duration = 0  # 0 for unlimited duration (duration in hours)
    max_choices = 0  # 0 for unlimited choices
    type = "standard"
    everyone_power = 1.0
    anonymous = False
