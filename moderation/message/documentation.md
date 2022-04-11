# Message Commands

Contains commands to send, edit and delete messages as the bot.


## `send`

Contains subcommands to send messages as the bot.

```css
.send
```

Required Permissions:

- `message.send`


### `text`

Sends normal text messages into a given text channel. After entering the command, the bot expects you to enter the text you want to send. If you have changed your mind, you can abort the process by entering `CANCEL`.

```css
.send [text|t] <channel>
```

Arguments:

| Argument  | Required                  | Description                                         |
|:---------:|:-------------------------:|:----------------------------------------------------|
| `channel` | :fontawesome-solid-check: | The channel into which you want to send the message |

Required Permissions:

- `message.send`


### `embed`

Sends embed messages into a given text channel. After entering the command, the bot expects you to enter the embed title. After entering the title, the bot asks for the description of the embed. If at any point you have changed your mind, you can abort the process by entering `CANCEL`.

```css
.send [embed|e] <channel> [color]
```

Arguments:

| Argument  | Required                  | Description                                         |
|:---------:|:----------------- -------:|:----------------------------------------------------|
| `channel` | :fontawesome-solid-check: | The channel into which you want to send the message |
| `color`   |                           | The color of the embed (name or hex code)           |

Required Permissions:

- `message.send`

!!! note
    - The title cannot contain more than 256 characters.
    - You cannot use user/role/channel mentions in embed titles


### `copy`

Copies the content, embeds and files of any message into a new message.

```css
.send [copy|c] <channel> <message>
```

Arguments:

| Argument  | Required                  | Description                                             |
|:---------:|:-------------------------:|:--------------------------------------------------------|
| `channel` | :fontawesome-solid-check: | The channel into which you want to send the new message |
| `message` | :fontawesome-solid-check: | The message you want to copy (specify the message link) |

Required Permissions:

- `message.send`


### `discohook`

Sends one or more messages specified by a [discohook.org](https://discohook.org/){target=_blank} link.

```css
.send [discohook|dh] <channel> <discohook_url>
```

Arguments:

| Argument        | Required                  | Description                                                                                        |
|:---------------:|:-------------------------:|:---------------------------------------------------------------------------------------------------|
| `channel`       | :fontawesome-solid-check: | The channel into which you want to send the message(s)                                             |
| `discohook_url` | :fontawesome-solid-check: | The [discohook.org](https://discohook.org/){target=_blank} link containing the messages to be sent |

Required Permissions:

- `message.send`


## `edit`

Contains subcommands to edit messages sent by the bot.

```css
.edit
```

Required Permissions:

- `message.edit`


### `text`

Edits normal text messages sent by the bot. After entering the command, the bot expects you to enter the new text. If you have changed your mind, you can abort the process by entering `CANCEL`.

```css
.edit [text|t] <message>
```

Arguments:

| Argument  | Required                  | Description                                             |
|:---------:|:-------------------------:|:--------------------------------------------------------|
| `message` | :fontawesome-solid-check: | The message you want to edit (specify the message link) |

Required Permissions:

- `message.edit`


### `embed`

Edits embed messages sent by the bot. After entering the command, the bot expects you to enter the new title. After entering the new title, the bot asks for the new description of the embed. If at any point you have changed your mind, you can abort the process by entering `CANCEL`.

```css
.edit [embed|e] <message> [color]
```

Arguments:

| Argument  | Required                  | Description                                                                                |
|:---------:|:-------------------------:|:-------------------------------------------------------------------------------------------|
| `message` | :fontawesome-solid-check: | The message you want to edit (specify the message link)                                    |
| `color`   |                           | The new color of the embed (name or hex code). If omitted, the embed color is not changed. |

Required Permissions:

- `message.edit`

!!! note
    - The title cannot contain more than 256 characters.
    - You cannot use user/role/channel mentions in embed titles


### `copy`

Copies the content, embeds and files of any message into another message already sent by the bot.

```css
.edit [copy|c] <message> <source>
```

Arguments:

| Argument  | Required                  | Description                                                  |
|:---------:|:-------------------------:|:-------------------------------------------------------------|
| `message` | :fontawesome-solid-check: | The message you want to edit (specify the message link)      |
| `source`  | :fontawesome-solid-check: | The message you want to copy from (specify the message link) |

Required Permissions:

- `message.edit`


### `discohook`

Edits a message sent by the bot and replaces it with the message specified by a [discohook.org](https://discohook.org/){target=_blank} link.

```css
.edit [discohook|dh] <message> <discohook_url>
```

Arguments:

| Argument        | Required                  | Description                                                                                             |
|:---------------:|:-------------------------:|:--------------------------------------------------------------------------------------------------------|
| `message`       | :fontawesome-solid-check: | The message you want to edit (specify the message link)                                                 |
| `discohook_url` | :fontawesome-solid-check: | The [discohook.org](https://discohook.org/){target=_blank} link containing the message to use as source |

Required Permissions:

- `message.edit`


## `delete`

Deletes any message.

```css
.delete <message>
```

Arguments:

| Argument  | Required                  | Description                                               |
|:---------:|:-------------------------:|:----------------------------------------------------------|
| `message` | :fontawesome-solid-check: | The message you want to delete (specify the message link) |

Required Permissions:

- `message.delete`


## `clear`

Deletes the last `n` messages in a given text channel.

```css
.[clear|clean] <count>
```

Arguments:

| Argument | Required                  | Description                               |
|:--------:|:-------------------------:|:------------------------------------------|
| `count`  | :fontawesome-solid-check: | The number of messages you want to delete |

Required Permissions:

- `message.clear`

!!! note
    You cannot delete more than 100 messages at once.


## `discohook`

Creates a [discohook.org](https://discohook.org/){target=_blank} link for one or more existing messages.

```css
.[discohook|dh] [messages...]
```

Arguments:

| Argument   | Required                  | Description                                                                                       |
|:----------:|:-------------------------:|:--------------------------------------------------------------------------------------------------|
| `messages` | :fontawesome-solid-check: | The messages you want to create a [discohook.org](https://discohook.org/){target=_blank} link for |
