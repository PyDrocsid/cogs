from PyDrocsid.pubsub import PubSubChannel

send_to_changelog = PubSubChannel()
send_alert = PubSubChannel()
log_auto_kick = PubSubChannel()
get_last_auto_kick = PubSubChannel()
get_user_info_entries = PubSubChannel()
get_user_status_entries = PubSubChannel()
get_userlog_entries = PubSubChannel()
revoke_verification = PubSubChannel()
can_respond_on_reaction = PubSubChannel()
