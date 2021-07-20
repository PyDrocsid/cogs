# Logging cog

This cog provides commands to set up the logging channels.


## `logging`


The `.logging` command is the main command for the logging cog. It uses 8 different subcommands, which also often have 2-3 subcommands.

If no subcommand is given, the .logging command shows the settings (channels, editing-range, etc)

```css
.[logging|log]
```


## `maxage`


The `.maxage` configures a period after which old log entries should be deleted.

```css
.logging [maxage|ma] <days>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`days`|:heavy_check_mark:|Time after which the old messages should be deleted|

If the value of `days` is set to `-1`, the deletion of the log entries is deactivated.


## `exclude`


The `.exclude` command excludes channel from the logging function.

```css
.logging [exclude|x|ignore|i] <add / remove> <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`add`|:heavy_check_mark:|Disables the log function for a channel|
|`remove`|:heavy_check_mark:|Activates the log function for a channel|
|`channel`|:heavy_check_mark:|The channel which should be in/excluded|


## Channel

A list of all channels with subcommands and purpose.


### Alart

Sends a message if an error occurs or if someone is channelhopping for example.

```css
.logging [alert|al|a]
```


### Changelog

Sends a message if some changes are made, for example creating a reaction role, kick, ban, report, mute, etc.

```css
.logging [changelog|change|cl|c]
```


### Message Edit

Sends a message if a message was edited.

```css
.logging [edit|e]
```


#### Edit mindist subcommand

Sets a number for the minimum ammount that has to be changed to activate the event.

```css
.logging [edit|e] [mindist|md] <mindist>
```


### Message Delete

Sends a message if a message was deleted.

```css
.logging [delete|d]
```


### Member Join

Sends a message if a user joined the server.

```css
.logging [member_join|memberjoin|join|mj]
```


### Member Leave

Sends a message if a user leaveded the server.

```css
.logging [member_leave|memberleave|leave|ml]
```


### *__Subcommands (Channel)__*


#### channel

Sets the channel for the log (Has to be used for enable the logging channels after disabling)

```css
.logging {Log-Channel} [channel|ch|c] <channel>
```


#### disable

Disables a channel

```css
.logging {Log-Channel} [disable|d]
```

