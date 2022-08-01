from PyDrocsid.settings import Settings


class PollsDefaultSettings(Settings):
    duration = 0  # 0 for max_duration duration (duration in hours)
    max_duration = 7  # max duration (duration in days)


class PollsTeamSettings(Settings):
    duration = 1  # days after which all missing team-members should be pinged, if not excluded
