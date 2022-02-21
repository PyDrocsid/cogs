# Content Filter

Contains commands to do set up checks for black listed expressions in every message.

!!! note
    User with the `content_filter.bypass` permission are not effected by the check.


## `content_filter`

Contains subcommands to do edit/show the content_filter. <br>

```css
.[content_filter|cf]
```

Required Permissions:

- `content_filter.read`


### `add`

This command is used to add a new expressions for the filter. <br>

```css
.content_filter [add|+] <regex> <delete> <description>
```

Arguments:

|   Argument    |         Required          | Description                                                                                |
|:-------------:|:-------------------------:|:-------------------------------------------------------------------------------------------|
|    `regex`    | :fontawesome-solid-check: | The [regex](https://regex101.com/) the filter should use                                   |
|   `delete`    | :fontawesome-solid-check: | True/False to indicate if the message should be deleted if a match for the regex was found |
| `description` | :fontawesome-solid-check: | A description for the entry (shown on the list)                                            |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


### `list`

This commands shows a list of every blacklisted expression. <br>

```css
.content_filter [list|l]
```

Required Permissions:

- `content_filter.read`


### `remove`

This command is used to remove an expressions from the filter. <br>

```css
.content_filter [remove|-] <pattern_id>
```

Arguments:

|   Argument   |         Required          | Description                                     |
|:------------:|:-------------------------:|:------------------------------------------------|
| `pattern_id` | :fontawesome-solid-check: | The ID from the command (shown by list command) |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


### `update`

Contains subcommands to do edit the content_filter. <br>

```css
.content_filter [update|u]
```

Required Permissions:
- `content_filter.read`
- `content_filter.write`


#### `description`

This command can be used to set a new description for an already existing filter.

```css
.content_filter update [description|d] <pattern_id> <new_description>
```

Arguments:

|     Argument      |         Required          | Description                                     |
|:-----------------:|:-------------------------:|:------------------------------------------------|
|   `pattern_id`    | :fontawesome-solid-check: | The ID from the command (shown by list command) |
| `new_description` | :fontawesome-solid-check: | The new description for the filter              |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


#### `regex`

This command can be used to edit the regex for an already existing filter.

```css
.content_filter update [regex|r] <pattern_id> <new_regex>
```

Arguments:

|   Argument   |         Required          | Description                                     |
|:------------:|:-------------------------:|:------------------------------------------------|
| `pattern_id` | :fontawesome-solid-check: | The ID from the command (shown by list command) |
| `new_regex`  | :fontawesome-solid-check: | The new regex for the filter to check for       |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


#### `toggle_delete`

This command can be used to toggle the delete-status for an already existing filter.

```css
.content_filter update [toggle_delete|td] <pattern_id>
```

Arguments:

|   Argument   |         Required          | Description                                     |
|:------------:|:-------------------------:|:------------------------------------------------|
| `pattern_id` | :fontawesome-solid-check: | The ID from the command (shown by list command) |

Required Permissions:

- `content_filter.read`
- `content_filter.write`
