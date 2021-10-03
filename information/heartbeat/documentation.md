# Heartbeat

This cog contains the heartbeat function, which sends a status embed to the bot owner every 20 seconds.

The information provided is the time the bot was started at and the time the bot last edited the embed at. When restarted, the bot sends a new embed, which is supposed to be edited until the bot is turned off. This is helpful for troubleshooting, for example if the bot freezes.

!!! Note
     To set the owner, you have to set `OWNER_ID` in the `.env` file.
