# Help

Contains the `.help` command, which can be used to get either a list of all available commands or detailed information about a specific command.


## `.help`

```css
.help [cog|command]
```

Arguments:

| Argument  | Required | Description                                                 |
|:---------:|:--------:|:------------------------------------------------------------|
| `cog`     |          | The cog whose command list is requested                     |
| `command` |          | The bot command for which detailed information is requested |


### Command List

You can either use `.help` to get a list of all commands grouped by cogs or `.help <cog>` to list all commands of a given cog.

!!! note
    The command list does not include commands that cannot be executed by the requesting user (e.g. due to missing permissions).


### Detailed Information

Detailed information about a given command is provided by executing `.help <command>`.

The information given by this command includes:

- Aliases
- Parameters
- Description
- Subcommands
- Required/Optional permissions
- Link to the PyDrocsid documentation
