# AutoClear

Contains functionality to delete messages that have exceeded a certain age from configured channels. Pinned messages are excluded from this and are not deleted.


## `autoclear`

Contains subcommands to manage the automatic message deletion. <br>
If not subcommand is given, this command shows a list of all configured channels with their respective TTLs (time to live) in minutes. Unpinned messages in one of those channels will be deleted when their age exceeds this TTL.

Usage:

```css
.[autoclear|ac]
```

Required Permissions:

- `autoclear.read`


### `set`

Configures the TTL for a given channel.

```css
.autoclear [set|s|add|a|+|=] <channel> <minutes>
```

Arguments:

| Argument  | Required                  | Description                                         |
|:---------:|:-------------------------:|:----------------------------------------------------|
| `channel` | :fontawesome-solid-check: | The channel for which AutoClear is to be configured |
| `minutes` | :fontawesome-solid-check: | The TTL in minutes                                  |

Required Permissions:

- `autoclear.read`
- `autoclear.write`

!!! note
    Messages cannot be deleted exactly after the configured time has elapsed, since the task for deleting old messages only runs every 5 minutes. In the worst case, a message will therefore be deleted 5 minutes after the configured TTL has been exceeded.


### `disable`

Disables AutoClear in a given channel.

```css
.autoclear [disable|d|delete|del|remove|r|-] <channel>
```

Arguments:

| Argument  | Required                  | Description                                      |
|:---------:|:-------------------------:|:-------------------------------------------------|
| `channel` | :fontawesome-solid-check: | The channel in which AutoClear is to be disabled |

Required Permissions:

- `autoclear.read`
- `autoclear.write`
