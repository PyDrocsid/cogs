# Sudo

This cog contains the `.sudo` command, as well as some other commands used to maintain the bot instance. This `.sudo` command is similar to the `sudo` command on Linux.


## `sudo`

The `.sudo` command allows a specific user to execute any command even without having the necessary permission level by temporarily granting the user the highest permission level (`owner`).

```css
.sudo <command>
```

To use this command your user ID has to match the value of the `OWNER_ID` environment variable. If this environment variable is not set, the Sudo cog is disabled.

!!! Hint
    If you have run a command without having the required permission level, you can use `.sudo !!` to rerun this command with `owner` privileges.


## Maintenance Commands

!!! Note
    These commands do not necessarily have to be executed with the `.sudo` command. Theoretically, the required permission levels can be changed to any other permission level, so that users who are not allowed to execute the `.sudo` command can also use these maintenance commands. However, it is recommended to only allow trusted users to use these commands.


### `clear_cache`

This command clears the redis cache by executing the `FLUSHALL` command.

```css
.reload_cache
```


### `reload`

This command reloads the bot by refiring all startup functions.

```css
.reload
```


### `stop`

This command stops the running bot instance gracefully.

```css
.stop
```


### `kill`

This command kills the running bot instance.

```css
.kill
```
