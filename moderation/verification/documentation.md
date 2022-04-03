# Verification

Contains a verification system that adds or removes certain roles from a member when they send the bot a command with a pre-set password via direct messages.


## `verification`

Shows the current verification configuration. This includes the roles that will be added to or removed from the member (verification roles), the configured password and the amount of time a member has to be in the server before they can verify.

```css
.[verification|vf]
```

Required Permissions:

- `verification.read`


### `add`

Adds a verification role. If you set `reverse` to `true`, the role will be removed from the member instead of being added. Note that verification will fail if the member does not have all reverse verification roles!

```css
.verification [add|a|+] <role> [reverse=False]
```

Arguments:

| Argument  | Required                  | Description                                          |
|:---------:|:-------------------------:|:-----------------------------------------------------|
| `role`    | :fontawesome-solid-check: | The verification role                                |
| `reverse` |                           | Remove this role instead of adding it to the member. |

Required Permissions:

- `verification.read`
- `verification.write`


### `remove`

Removes an existing verification role.

```css
.verification [remove|r|-] <role>
```

Arguments:

| Argument | Required                  | Description           |
|:--------:|:-------------------------:|:----------------------|
| `role`   | :fontawesome-solid-check: | The verification role |

Required Permissions:

- `verification.read`
- `verification.write`


### `password`

Sets the *secret* password the member will need to verify with.

```css
.verification [password|p] <password>
```

Arguments:

| Argument   | Required                  | Description  |
|:----------:|:-------------------------:|:-------------|
| `password` | :fontawesome-solid-check: | The password |

Required Permissions:

- `verification.read`
- `verification.write`

!!! note
    The password has a maximum length of 256 characters.


### `delay`

Sets the amount of time a member has to be in the server before they can verify.

```css
.verification [delay|d] <seconds>
```

Arguments:

| Argument | Required                  | Description                   |
|:--------:|:-------------------------:|:------------------------------|
| `delay`  | :fontawesome-solid-check: | The amount of time in seconds |

Required Permissions:

- `verification.read`
- `verification.write`


## `verify`

Allows server members to verify themselves. If the specified password is correct and the configured delay has elapsed, the configured verification roles will be added to or removed from the member.

```css
verify <password>
```

Arguments:

| Argument   | Required                  | Description               |
|:----------:|:-------------------------:|:--------------------------|
| `password` | :fontawesome-solid-check: | The verification password |

!!! note
    As this command can only be used in direct messages, it does not start with the configured bot prefix! So, for example, if the configured password is `Tr0ub4dor&3`, a member would have to send this exact message to the bot to complete verification:
    <!-- markdownlint-disable-next-line MD038 -->
    ```
    verify Tr0ub4dor&3
    ```
