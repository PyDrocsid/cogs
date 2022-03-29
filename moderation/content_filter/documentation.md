# Content Filter

Contains commands to setup a list of regular expressions, which will be filtered in every message.

!!! note
    Users with the `content_filter.bypass` permission are not affected by these checks.


## `content_filter`

Contains subcommands to manage the content filter.
If no subcommand is given, a list with all blacklisted expressions will be shown.

```css
.[content_filter|cf]
```

Required Permissions:

- `content_filter.read`


### `add`

Adds a new regular expression to the filter.

```css
.content_filter [add|a|+] <regex> <delete> <description>
```

Arguments:

| Argument      | Required                  | Description                                                                                |
|:-------------:|:-------------------------:|:-------------------------------------------------------------------------------------------|
| `regex`       | :fontawesome-solid-check: | The [regex](https://regex101.com/) the filter should use                                   |
| `delete`      | :fontawesome-solid-check: | True/False to indicate if the message should be deleted if a match for the regex was found |
| `description` | :fontawesome-solid-check: | A description for the entry (shown in the list)                                            |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


### `remove`

Removes a regular expression from the filter.

```css
.content_filter [remove|del|r|d|-] <pattern>
```

Arguments:

| Argument  | Required                  | Description                            |
|:---------:|:-------------------------:|:---------------------------------------|
| `pattern` | :fontawesome-solid-check: | The ID of the pattern (shown by `.cf`) |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


### `update`

Contains subcommands to edit the content filter.

```css
.content_filter [update|u]
```

Required Permissions:

- `content_filter.read`
- `content_filter.write`


#### `description`

Sets a new description for an existing filter.

```css
.content_filter update [description|d] <pattern> <new_description>
```

Arguments:

| Argument          | Required                  | Description                            |
|:-----------------:|:-------------------------:|:---------------------------------------|
| `pattern`         | :fontawesome-solid-check: | The ID of the pattern (shown by `.cf`) |
| `new_description` | :fontawesome-solid-check: | The new description for the filter     |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


#### `regex`

Edits the regular expression of an existing filter.

```css
.content_filter update [regex|r] <pattern> <new_regex>
```

Arguments:

| Argument    | Required                  | Description                               |
|:-----------:|:-------------------------:|:------------------------------------------|
| `pattern`   | :fontawesome-solid-check: | The ID of the pattern (shown by `.cf`)    |
| `new_regex` | :fontawesome-solid-check: | The new regex for the filter to check for |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


#### `delete_message`

Changes whether to delete messages matched by an existing filter.

```css
.content_filter update [delete_message|del|del_message|dm] <pattern> <delete>
```

Arguments:

| Argument  | Required                  | Description                                                                                |
|:---------:|:-------------------------:|:-------------------------------------------------------------------------------------------|
| `pattern` | :fontawesome-solid-check: | The ID of the pattern (shown by `.cf`)                                                     |
| `delete`  | :fontawesome-solid-check: | True/False to indicate if the message should be deleted if a match for the regex was found |

Required Permissions:

- `content_filter.read`
- `content_filter.write`


### `check`

Checks if a given regex matches a specific string.

```css
.content_filter [check|c] <pattern> <test_string>
```

Arguments:

| Argument      | Required                  | Description                                                                                    |
|:-------------:|:-------------------------:|:-----------------------------------------------------------------------------------------------|
| `pattern`     | :fontawesome-solid-check: | A regex, the id of an existing pattern (shown by `.cf`) or `-1` to check all existing patterns |
| `test_string` | :fontawesome-solid-check: | A test string                                                                                  |

Required Permissions:

- `content_filter.read`
