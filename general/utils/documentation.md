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

```css
.[snowflake|sf|time] <ID>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`ID`|:heavy_check_mark:|The snowflake ID|


## `encode`

The `.encode` command applies Python's [`str.encode` function](https://docs.python.org/3/library/stdtypes.html#str.encode){target=_blank} to the username and nickname of a given user.

Usage:

```css
.[encode|enc] <user>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user or member|


## `suggest_role_color`

The `.suggest_role_color` command suggests the color for a new role, trying to avoid colors already in use. Optionally you can specify a list of colors to also avoid.

Usage:

```css
.[suggest_role_color|rc] [avoid...]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`avoid`| |A list of color hex codes to avoid|
