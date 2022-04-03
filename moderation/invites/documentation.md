# Invite Whitelist

Contains commands to manage a whitelist for discord invites that may be sent in the chat. Invites not on the list will be deleted automatically.


## `invites`

Contains subcommands to manage the whitelist of allowed discord servers.

```css
.[invites|i]
```


### `list`

Returns a list of all Discord servers on the whitelist.

```css
.invites [list|l|?]
```


### `show`

Shows detailed information about a given server on the whitelist.

```css
.invites [show|info|s|i] <server>
```

Arguments:

| Argument | Required                  | Description                     |
|:--------:|:-------------------------:|:--------------------------------|
| `server` | :fontawesome-solid-check: | The server's name, id or invite |


### `add`

Adds a Discord server to the whitelist.

```css
.invites [add|+|a] <invite> <applicant>
```

Arguments:

| Argument    | Required                  | Description                                                 |
|:-----------:|:-------------------------:|:------------------------------------------------------------|
| `invite`    | :fontawesome-solid-check: | The invite link (should be permanent with unlimited usages) |
| `applicant` | :fontawesome-solid-check: | The user who wants to add the server to the list            |

Required Permissions:

- `invites.manage`


### `remove`

Removes a server from the whitelist.

```css
.invites [remove|r|del|d|-] <server>
```

Arguments:

| Argument | Required                  | Description                     |
|:--------:|:-------------------------:|:--------------------------------|
| `server` | :fontawesome-solid-check: | The server's name, id or invite |

Required Permissions:

- `invites.manage`


### `update`

Contains subcommands to update the invite link and description of a server on the whitelist.

```css
.invites [update|u]
```

!!! note
    These commands can be used by the applicant of the respective server as well as by anyone who has the `invites.manage` permission.


#### `description`

Changes the description of a server on the whitelist.

```css
.invites update [description|d] <server> [description]
```

Arguments:

| Argument      | Required | Description                                                          |
|:-------------:|:--------:|:---------------------------------------------------------------------|
| `description` |          | The new description. If omitted, the current description is cleared. |


#### `invite`

Updates the invite link to a server on the whitelist.

```css
.invites update [invite|i] <invite>
```

Arguments:

| Argument | Required                  | Description                                                     |
|:--------:|:-------------------------:|:----------------------------------------------------------------|
| `invite` | :fontawesome-solid-check: | The new invite link (should be permanent with unlimited usages) |
