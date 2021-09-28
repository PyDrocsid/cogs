# Verification

This cog is used to add a verification system that adds or removes certain roles from a member when they send the bot a command with a pre-set password via direct messages.


## `verification`

The `.verification` command shows the current verification configuration. This includes the roles that will be added to or removed from the member (verification roles), the configured password and the amount of time a member has to be in the server before they can verify.


### `add`

The `add` subcommand adds a verification role. If you set `reverse` to `true`, the role will be removed from the user instead of being added. Note that verification will fail if the user does not have all reverse verification roles!

```css
.verification [add|a|+] <role> [reverse=False]
```

Argument|Required|Description
|:------:|:------:|:----------|
`role`|:heavy_check_mark:|The verification role
`reverse`|       |Remove this role instead of adding it to the user.

Required permissions:

- `verification.read`
- `verification.write`


### `remove`

The `remove` subcommand removes an existing verification role.

```css
.verification [remove|r|-] <role>
```

Argument|Required|Description
|:------:|:------:|:----------|
`role`|:heavy_check_mark:|The verification role

Required permissions:

- `verification.read`
- `verification.write`


### `password`

The `password` subcommand sets the *secret* password the user will need to verify with.

```css
.verification [password|p] <password>
```

Argument|Required|Description
|:------:|:------:|:----------|
`password`|:heavy_check_mark:|The password

Required permissions:

- `verification.read`
- `verification.write`

!!! note
    The password has a maximum length of 256 characters.


### `delay`

The `delay` subcommand sets the amount of time a member has to be in the server before they can verify.

```css
.verification [delay|d] <seconds>
```

Argument|Required|Description
|:------:|:------:|:----------|
`delay`|:heavy_check_mark:|The amount of time in seconds

Required permissions:

- `verification.read`
- `verification.write`


## `verify`

The `verify` command is used by server members to verify themselves. If the specified password is correct and the configured delay has elapsed, the configured verification roles will be added to or removed from the member.

```css
verify <password>
```

Argument|Required|Description
|:------:|:------:|:----------|
`password`|:heavy_check_mark:|The verification password

!!! note
    As this command can only be used in direct messages, it does not start with the configured bot prefix! So, for example, if the configured password is `Tr0ub4dor&3`, a member would have to send this exact message to the bot to complete verification:
    <!-- markdownlint-disable-next-line MD038 -->
    ```
    verify Tr0ub4dor&3
    ```
