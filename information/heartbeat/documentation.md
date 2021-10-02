# Heartbeat

This cog contains the heartbeat function, which sends a status embed every 20 seconds to the bot-owner.

The information provided is the time the bot started and the time when the bot last edited the embed. Restarting sends a new embed, which is supposed to be edited until the bot is turned off. This is helpful for troubleshooting, for example when the bot froze.

!!! Note
     To set the owner, you have to set the `OWNER_ID=<your_id>` in the.env file, where the token is also located.
