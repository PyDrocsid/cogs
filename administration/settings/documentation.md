# Settings

This cog contains commands to change various settings of the bot.

## `prefix`
The `.prefix` command can be used to change the bot prefix. Any message containing a command has to start with this prefix, directly followed by the command itself.

!!! note
    When messaging the bot directly you can (but don't have to) omit the prefix.

You can change the prefix by using:

```css
.prefix <new_prefix>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`new_prefix`|:heavy_check_mark:|The new prefix|

!!! note
    - The prefix cannot contain more than 16 characters.
    - Only alphanumeric and punctuation characters are allowed.
