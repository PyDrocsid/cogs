# Message Commands

This cog contains commands to send and manage messages as the bot.

## `send`
The `.send` command can be used to send messages as the bot. There are three different subcommands.

### `text`
You can send normal text messages in a channel by using:

```css
.send [text|t] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel into which you want to send the message|

After entering the command, the bot expects you to enter the text you want to send. If you have changed your mind, you can abort the process by entering `CANCEL`.

### `embed`
You can send embed messages in a channel by using:

```css
.send [embed|e] <channel> [color]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel into which you want to send the message|
|`color`||The color of the embed (name or hex code)|

After entering the command, the bot expects you to enter the embed title. 

!!! note
    - The title cannot contain more than 256 characters.
    - You cannot use user/role/channel mentions in embed titles

After entering the title, the bot asks for the description of the embed.

If at any point you have changed your mind, you can abort the process by entering `CANCEL`.

### `copy`
You can copy the content, embeds and files of any message into a new message by using:

```css
.send [copy|c] <channel> <message>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel into which you want to send the new message|
|`message`|:heavy_check_mark:|The message you want to copy (specify the message link)|

## `edit`
The `.edit` command can be used to edit messages sent by the bot.

### `text`
You can edit normal text messages sent by the bot by using:

```css
.edit [text|t] <message>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`message`|:heavy_check_mark:|The message you want to edit (specify the message link)|

After entering the command, the bot expects you to enter the new text. If you have changed your mind, you can abort the process by entering `CANCEL`.

### `embed`
Use this command to edit embed messages sent by the bot by using:

```css
.edit [embed|e] <message> [color]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`message`|:heavy_check_mark:|The message you want to edit (specify the message link)|
|`color`||The new color of the embed (name or hex code)|

After entering the command, the bot expects you to enter the new title.

!!! note
    - The title cannot contain more than 256 characters.
    - You cannot use user/role/channel mentions in embed titles

After entering the new title, the bot asks for the new description of the embed.

If at any point you have changed your mind, you can abort the process by entering `CANCEL`.

### `copy`
You can copy the content, embeds and files of any message into another message already sent by the bot by using:

```css
.edit [copy|c] <message> <source>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`message`|:heavy_check_mark:|The message you want to edit (specify the message link)|
|`source`|:heavy_check_mark:|The message you want to copy from (specify the message link)|

## `delete`
Use this command to delete any message:

```css
.delete <message>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`message`|:heavy_check_mark:|The message you want to delete (specify the message link)|
