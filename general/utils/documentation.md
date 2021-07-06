# Utils

This cog contains some utility commands for general use as well as for testing and development.


## `ping`

The `.ping` command can be used to determine the latency of the bot to Discord in milliseconds.

Usage:

```css
.ping
```


## `snowflake`

The `.snowflake` command extracts and displays the timestamp from any [Discord snowflake ID](https://discord.com/developers/docs/reference#snowflakes){target=_blank}. It can be used to find out the date and time of creation of any Discord user, guild, channel, message, role, custom emoji or anything else that has an ID.

Usage:

```.css
.[snowflake|sf|time] <ID>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`ID`|:heavy_check_mark:|The snowflake ID|
