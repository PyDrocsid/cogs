# Heartbeat

This cog contains the heartbeat function, which sends a status embed to the bot owner every 20 seconds.

The information given is when the bot was last started and when it last updated the embed. With each restart, a new embed is sent, which the bot edits every 20 seconds until it is switched off. This is helpful for troubleshooting, for example if the bot freezes.

!!! Note
     To set the owner, you have to set `OWNER_ID` in the `.env` file.
