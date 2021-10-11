# Custom Commands

This cog contains the `custom_commands` command, which can be used to create simple commands that send a predefined answer when used.


## custom_commands

The `.custom_commands` command contains different sub commands to create, edit and delete custom commands.

```css
.[custom_commands|cc] [subcommand]
```

If no subcommand is given, a list of all avaiable custom commands with aliases will be send.


### `add`

The `add` subcommand is used to create new custom commands.

```css
.custom_commands [add|+] <name> <discohook_url> [public=True]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`name`|:heavy_check_mark:|The custom command's name|
|`discohook_url`|:heavy_check_mark:|Go to [this side](https://discohook.org/), compose your message, click on `Share Message` and copy the link|
|`public`|        |If set to `False`, the custom command's permission level will be set to the bot's default permission level|


### `alias`

The `alias` subcommand is used to add an alias to a custom command.

```css
.custom_commands [alias|a] <command> <alias>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The custom command's name|
|`alias`|:heavy_check_mark:|The alias to be added to the custom command|


### `edit`

The `edit` subcommand contains various subcommands to edit an existing custom command.

```css
.custom_commands [edit|e] [subcommand] 
```

If no subcommand is given, a list of all subcommands for `edit` will be sent.


#### `channel`

The `channel` subcommand is used to specify a channel the custom command's answer should be sent to by default.

```css
.custom_commands edit [channel|c] <command> [channel]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The custom command's name|
|`channel`|       |The channel the custom command's answer should be sent to. If no channel is given, the message will be sent to the channel the custom command is executed in|


#### `channel_parameter`

The `channel_parameter` subcommand is used to enable or disable the custom command's `channel` parameter.

```css
.custom_commands edit [channel_parameter|cp] <command> <enabled>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`enabled`|:heavy_check_mark:|True/False to enable/disable the `channel` parameter|


#### `delete_command`

The delete_command subcommand is used to specifie if the command should be deleted after the execution.

```css
.custom_commands edit [delete_command|dc] <command> <delete>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`delete`|:heavy_check_mark:|True/False to enable/disable the deletion|


#### `description`

The description subcommand is used to set an description for a custom command.

```css
.custom_commands edit [description|desc|d] <command> [description]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`description`|       |The description. The description can be removed by leaving this argument empty|


#### `enabled`

The enabled subcommand is used to enable/disable the command.

```css
.custom_commands edit [enabled|e] <command> <enabled>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`enabled`|:heavy_check_mark:|True/False to enable/disable the command|


#### `name`

The name subcommand is used to change the name of the custom command.

```css
.custom_commands edit [name|n] <command> <name>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`name`|:heavy_check_mark:|The new name for the command|


#### `permission_level`

The permission_level subcommand is used to set the required permission level to execute the custom command.

```css
.custom_commands edit [permission_level|pl] <command> <level>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`level`|:heavy_check_mark:|The new permission level (0-4)|


#### `requires_confirmation`

The requires_confirmation subcommand is used to specify whether to send a confirmation message before sending the message of the custom command.

```css
.custom_commands edit [requires_confirmation|rc] <command> <enabled>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`enabled`|:heavy_check_mark:|True/False to enable/disable the confimation|


#### `text`

The text subcommand is used to edit the content of the message.

```css
.custom_commands edit [text|t|content|data] <command> <discohook_url>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`text`|:heavy_check_mark:|Go to [this side](https://discohook.org/), compose your message, click on `Share Message` and copy the link.|


#### `user_parameter`

The user_parameter subcommand is used to enable/disable the mention of a user on top of the message.

```css
.custom_commands edit [user_parameter|up] <command> <enabled>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|
|`enabled`|:heavy_check_mark:|True/False to enable/disable the user parameter|


### `remove`

The remove subcommand is used to remove a custom command.

```css
.custom_commands [remove|r|del|d|-] <command>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|


### `show`

The show subcommand is used to show all information about a custom command.

```css
.custom_commands [show|s|view|v|?] <command>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|


### `test`

The test subcommand is used to send a preview of the message without mentioning roles/user.

```css
.custom_commands [test|t] <command>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`command`|:heavy_check_mark:|The name of the custom command|


### `unalias`

The `unalias` subcommand is used to remove an alias from a custom command.

```css
.custom_commands [unalias|u] <alias>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`alias`|:heavy_check_mark:|The alias' name|


### Execution of custom commands

```css
.<name|alias> <channel> [user]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`name/alias`|:heavy_check_mark:|A custom command's name or alias|
|`channel`|       |The channel to send the custom command's answer to. Required if the custom command's `channel` parameter is enabled|
|`user`|       |If activated, you can set a user to be mentioned with the custom command's answer|
