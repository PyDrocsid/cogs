# MediaOnly

This cog contains the `mediaonly` command to set up and manage channels only pictures can be sent to.


## `list`

The `list` subcommand shows a list of all media-only channels.

```css
.mediaonly [list|l|?]
```

Required Permissions:

- `mediaonly.read`


## `add`

The `add` subcommand sets the media-only flag for a given text channel.

```css
.mediaonly [add|a|+] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel|

Required Permissions:

- `mediaonly.read`
- `mediaonly.write`

!!! note
    Responses to [slash commands](https://blog.discord.com/slash-commands-are-here-8db0a385d9e6){target=_blank} are ignored by the bot, so you should disable slash commands manually in media-only channels.


## `remove`

The `remove` subcommand removes the media-only flag from a given text channel.

```css
.mediaonly [remove|del|r|d|-] <channel>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`channel`|:heavy_check_mark:|The channel|

Required Permissions:

- `mediaonly.read`
- `mediaonly.write`
