# MediaOnly

Contains the `mediaonly` command to set up and manage channels only pictures can be sent to.


## `mediaonly`

Contains subcommands to manage media-only channels. <br>
If no subcommand is given, this command shows a list of all media-only channels.

```css
.[mediaonly|mo]
```

Required Permissions:

- `mediaonly.read`


### `add`

Sets the media-only flag for a given text channel.

```css
.mediaonly [add|a|+] <channel>
```

Arguments:

| Argument  | Required                  | Description |
|:---------:|:-------------------------:|:------------|
| `channel` | :fontawesome-solid-check: | The channel |

Required Permissions:

- `mediaonly.read`
- `mediaonly.write`

!!! note
    Responses to [slash commands](https://blog.discord.com/slash-commands-are-here-8db0a385d9e6){target=_blank} are ignored by the bot, so you should disable slash commands manually in media-only channels.


### `remove`

Removes the media-only flag from a given text channel.

```css
.mediaonly [remove|del|r|d|-] <channel>
```

Arguments:

| Argument  | Required                  | Description |
|:---------:|:-------------------------:|:------------|
| `channel` | :fontawesome-solid-check: | The channel |

Required Permissions:

- `mediaonly.read`
- `mediaonly.write`
