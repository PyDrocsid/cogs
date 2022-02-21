# Sudo

Contains the `.sudo` command, as well as some other commands used to maintain the bot instance.


## `sudo`

Allows a specific user to execute any command even without having the necessary permission level by temporarily granting the user the highest permission level (similar to the `sudo` command on Linux).

```css
.sudo <command>
```

Arguments:

| Argument  | Required                  | Description                                  |
|:---------:|:-------------------------:|:--------------------------------------------:|
| `command` | :fontawesome-solid-check: | The command to execute with owner privileges |

!!! note
    To use this command your user ID has to match the value of the `OWNER_ID` environment variable. If this environment variable is not set, the Sudo cog is disabled.

!!! Hint
    If you have run a command without having the required permission level, you can use `.sudo !!` to rerun this command with `owner` privileges.


## Maintenance Commands

!!! note
    These commands do not necessarily have to be executed with the `.sudo` command. Theoretically, the required permission levels can be changed to any other permission level, so that users who are not allowed to execute the `.sudo` command can also use these maintenance commands. However, it is recommended to only allow trusted users to use these commands.


### `clear_cache`

Clears the redis cache by executing the `FLUSHDB` command.

```css
.clear_cache
```

Required Permissions:

- `sudo.clear_cache`


### `reload`

Reloads the bot by refiring all startup functions.

```css
.reload
```

Required Permissions:

- `sudo.reload`


### `stop`

Stops the running bot instance gracefully.

```css
.stop
```

Required Permissions:

- `sudo.stop`


### `kill`

Kills the running bot instance.

```css
.kill
```

Required Permissions:

- `sudo.kill`
