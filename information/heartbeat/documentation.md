# Heartbeat

This cog cointains the heartbeat-function, wich sends a status embed every 20 seconds to the bot-owner.

The information provided by the embed is the time of the last start of the bot and the time when the bot last edited the embed. Turning the bot off and on again sends a new embed, which is edited (ideally) until the bot is turned off. This is helpful in troubleshooting, for example when the bot has gone out or hung up, because you can then determine with a 20second margin when it last worked properly

!!! Note
     To set the owner, you have to set the `OWNER_ID=<your_id>` in the.env file, where the token is also located.
