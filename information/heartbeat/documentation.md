# Heartbeat

This cog contains the heartbeat function, which sends a status embed to the bot owner every 20 seconds.

The information provided is the time the bot started and the time when the bot last edited the embed. Restarting sends a new embed, which is supposed to be edited until the bot is turned off. This is helpful for troubleshooting, for example when the bot froze.

!!! Note
     To set the owner, you have to set `OWNER_ID` in the `.env` file.
