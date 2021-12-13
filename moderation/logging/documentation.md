# Logging cog

This cog provides commands to set up the logging channels.


## `logging`


The `.logging` command is the main command of the logging cog. It uses 8 different subcommands, which also often have 2-3 subcommands.

If no subcommand is given, the command shows the settings (channels, editing range, etc).

```css
.[logging|log]
```


## `maxage`


The `.maxage` command configures a period after which old log entries should be deleted.

```css
.logging [maxage|ma] <days>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`days`|:heavy_check_mark:|Time after which the old messages should be deleted|

If the value of `days` is set to `-1`, the deletion of the log entries is disabled.


## `exclude`


The `.exclude` command excludes a channel from the logging function. It has 2 subcommands.

If no subcommand is given, the command shows a list with excluded channels.

```css
.logging [exclude|x|ignore|i]
```


### add


Disables the log function for a channel.

```css
.logging exclude [add|a|+] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel which should be excluded from logging|


### remove

Enables the log function for a channel.

```css
.logging exclude [remove|r|del|d|-] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel which should be included in logging|


## `alert`

Sends a message if an error occurs or e.g. if someone is moving through various channels.

```css
.logging [alert|al|a]
```


### channel

Sets the channel for the log (has to be used to enable the logging channels after disabling).

```css
.logging alert [channel|ch|c] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel which should be used for the alert log|


### disable

Disables alert event logging.

```css
.logging alert [disable|d]
```


## `changelog`

Sends a message if some changes are made, for example creating a reaction role, kick, ban, report, mute, etc.

```css
.logging [changelog|change|cl|c]
```


### channel

Sets the channel for the log (has to be used to enable the logging channels after disabling).

```css
.logging changelog [channel|ch|c] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel which should be used for the changelog log|


### disable

Disables changelog event logging.

```css
.logging changelog [disable|d]
```


## `edit`

Sends a message if a message was edited.

```css
.logging [edit|e]
```


### channel

Sets the channel for the log (has to be used to enable the logging channels after disabling).

```css
.logging edit [channel|ch|c] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel which should be used for the edit log|


### disable

Disables edit event logging.

```css
.logging edit [disable|d]
```


### mindist

Sets a number for the minimum ammount that has to be changed to activate the event.

```css
.logging [edit|e] [mindist|md] <mindist>
```


## `delete`

Sends a message if a message was deleted.

```css
.logging [delete|d]
```


### channel

Sets the channel for the log (Has to be used for enable the logging channels after disabling)

```css
.logging delete [channel|ch|c] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel which should be used for the delete log|


### disable

Disables delete event logging.

```css
.logging delete [disable|d]
```


## `member_join`

Sends a message if a user joined the server.

```css
.logging [member_join|memberjoin|join|mj]
```


### channel

Sets the channel for the log (Has to be used for enable the logging channels after disabling)

```css
.logging member_join [channel|ch|c] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel which should be used for the member_join log|


### disable

Disables member_join event logging.

```css
.logging member_join [disable|d]
```


## `member_leave`

Sends a message if a user left the server.

```css
.logging [member_leave|memberleave|leave|ml]
```


### channel

Sets the channel for the log (Has to be used for enable the logging channels after disabling)

```css
.logging member_leave [channel|ch|c] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel which should be used for the member_leave log|


### disable

Disables member_leave logging.

```css
.logging member_leave [disable|d]
```
