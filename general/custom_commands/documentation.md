# custom commands

This cog contains the `custom_commands` command. The command can be used to create own commands which can be called.

This command contains different sub commands to create/edit/delete custom commands.

```css
.[custom_commands|cc] [subcommand]
```

If no subcommand is given a list of all avaiable custom commands with aliasses will be send.


## `add`

This subcommand is used to create new custom commands.

```css
.custom_commands [add|+] <name> <discohook_url> [public=True]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`name`|:heavy_check_mark:|The name of the custom command|
|`discohook_link`|:heavy_check_mark:|Go to https://discohook.org/, compose your message, click on `Share Message` and copy the link.|
|`public`||If set to `False` the permission level of the command will be set to the default permission level of the bot|


## `alias`

This subcommand adds an alias to a command

```css
.custom_commands [alias|a] <command> <alias>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`alias`|:heavy_check_mark:|The alias which should be added to the command|


## `edit`

This subcommand has some own subcommands to edit different things.

```css
.custom_commands [edit|e] [subcommand] 
```

If no subcommand is given a list oif all subcommands for `edit` will be send


### __`channel`__

This command specifies a channel in which the commnand should be send by default

```css
.custom_commands edit [channel|c] <command> [channel]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`channel`||The channel in which the message should be send. If no channel is given the message will be send to the channel from the executed command|


### __`channel_parameter`__

This command specifies a channel in which the commnand should be send by default.

```css
.custom_commands edit [channel_parameter|cp] <command> <enabled>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`enabled`|:heavy_check_mark:|True/False to enable/disable the `channel` parameter|


### __`delete_command`__

This command specifies if the command should be deleted after the execution.

```css
.custom_commands edit [delete_command|dc] <command> <delete>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`delete`|:heavy_check_mark:|True/False to enable/disable the deletion|


### __`description`__

This command sets an description for a custom command.

```css
.custom_commands edit [description|desc|d] <command> [description]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`description`||The text for the description. The discription can be removed by leaving the description param empty|


### __`enable`__

This command enables/disables the command.

```css
.custom_commands edit [enabled|e] <command> <enabled>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`enabled`|:heavy_check_mark:|True/False to enable/disable the command|


### __`name`__

This command chnages the name of the custom command.

```css
.custom_commands edit [name|n] <command> <name>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`name`|:heavy_check_mark:|The new name for the command|


### __`permission_level`__

This command sets the requiered permission level to execute the custom command.

```css
.custom_commands edit [permission_level|pl] <command> <level>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`level`|:heavy_check_mark:|The new permission level (0-4)|


### __`requires_confirmation`__

This command enables/disables a confirmation message before sending the message of the custom command.

```css
.custom_commands edit [requires_confirmation|rc] <command> <enabled>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`enabled`|:heavy_check_mark:|True/False to enable/disable the confimation|


### __`text`__

This command edits the content of the message.

```css
.custom_commands edit [text|t|content|data] <command> <discohook_url>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`text`|:heavy_check_mark:|Go to https://discohook.org/, compose your message, click on `Share Message` and copy the link.|


### __`user_parameter`__

This command enables/disables the mention of a user on top of the message.

```css
.custom_commands edit [user_parameter|up] <command> <enabled>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`enabled`|:heavy_check_mark:|True/False to enable/disable the user parameter|


## `remove`

This command removes a custom command.

```css
.custom_commands [remove|r|del|d|-] <command>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|


## `show`

This command shows all information about a custom command.

```css
.custom_commands [show|s|view|v|?] <command>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|


## `test`

This command send a preview of the message without mentioning roles/user. 

```css
.custom_commands [test|t] <command>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|


## `unalias`

This command removes an alias from a custom command.

```css
.custom_commands [unalias|u] <alias>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`alias`|:heavy_check_mark:|The name of the alias|


# Execution of custom commands

```css
.<name|alias> <channel> [user]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`name|alias`|:heavy_check_mark:|The name or the alias of a custom command|
|`channel`|:heavy_check_mark:|If activated you have to name a channel in which the message should be send|
|`user`||If activated you can set a user which will be mentioned|
