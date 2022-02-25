# Settings

Contains commands to change various settings of the bot.


## `prefix`

Changes the bot prefix. Any message containing a command has to start with this prefix, directly followed by the command itself. When messaging the bot directly you can (but don't have to) omit the prefix.

```css
.prefix <new_prefix>
```

Arguments:

| Argument     | Required                  | Description    |
|:------------:|:-------------------------:|:---------------|
| `new_prefix` | :fontawesome-solid-check: | The new prefix |

Required Permissions:

- `settings.change_prefix`

!!! note
    - The prefix cannot contain more than 16 characters.
    - Only alphanumeric and punctuation characters are allowed.
