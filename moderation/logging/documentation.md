# Logging Cog

This cog provides commands to setup the logging channels.


## `logging`


The `.logging` command is the parent command for the logging category. He uses different sub-commands, which also often have sub-commands.

If no subcommand is given, the `.logging` command shows the settings (Channels, edeting-range, etc)

```css
.[logging|log] [subcommand]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`subcommand`||The subbcommand|


## *Subcommands*


## `maxage`


The maxage configures a period after which old log entries should be deletet. If the `days` parameter is set to `-1` the deleting after time is disabled.

```css
.logging [maxage|ma] <days>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`days`|:heavy_check_mark:|Time after which the old messages should be deleted|


## `exclude`


This command excludes channel from the logging function.

```css
.logging [exclude|x|ignore|i] <add / remove> <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`add / remove`|:heavy_check_mark:|Indicates if a channel should be added (excluded) or removed (included) in the list of channels which are logged|
|`channel`|:heavy_check_mark:|The channel which should be in/excluded|


## Channel


A list of all channels with subcommands and purpose.

|Name|Log-Channel|Purpose|
|:------:|:------:|:----------|
|Alert|`[alert/al/a]`|Sends a masse if an error occurs or if someone is channelhopping for example|
|Changelog|`[changelog/change/cl/c]`|Sends a message if some changes are made, for example crating a reaction role, kick, ban, report, mute, etc|
|Message Edit|`[edit/e]`|Sends a message if a message was edited|
|Message Delete|`[delete/d]`|Sends a message if a message was deleted|
|Member Join|`[member_join/memberjoin/join/mj]`|Sends a message if a user joined the server|
|Member Leave|`[member_leave/memberleave/leave/ml]`|Sends a message if a user leaved the server|


## *__Subcommands (Channel)__*


|Command|Argument|Description|
|:------:|:------:|:----------|
|`.logging {Log-Channel} [channel/ch/c] <channel>`| channel |Sets the channel for the log (Has to be used for enable the logging channels after disabling)|
|`.logging {Log-Channel} [disable/d]`||Disables a channel|
|`.logging [edit/e] [mindist/md] <mindist>`|mindist|Changes the minimum edit distance between the olf and the new content of the message to be logged (Only for the Message-Edit-Channel)|
