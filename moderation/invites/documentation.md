# Invite Whitelist

This cog provides commands to manage a whitelist for discord invites that may be sent in the chat and automatic deletion of invites not on the list.


## `list`

The `.list` command returns a list of all Discord servers on the whitelist.

```css
.[invites|i] [list|l|?]
```


## `show`

The `.show` command shows detailed information about a given server on the whitelist.

```css
.[invites|i] [show|info|s|i] <server>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|server|:fontawesome-solid-check:|The server's name, id or invite|


## `add`

The `.add` command adds a Discord server to the whitelist.

```css
.[invites|i] [add|+|a] <invite> <applicant>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|invite|:fontawesome-solid-check:|The invite link (should be permanent with unlimited usages)|
|applicant|:fontawesome-solid-check:|The user who wants to add the server to the list|

Required Permissions:

- `invites.manage`


## `remove`

The `.remove` command removes a server from the whitelist.

```css
.[invites|i] [remove|r|del|d|-] <server>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|server|:fontawesome-solid-check:|The server's name, id or invite|

Required Permissions:

- `invites.manage`


## `update`

The `.update` command allows the applicant and users with the `invites.manage` permission to update the invite link to a server on the whitelist.

```css
.[invites|i] [update|u] <invite>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|invite|:fontawesome-solid-check:|The new invite link (should be permanent with unlimited usages)|
