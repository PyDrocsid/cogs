# BeTheProfessional

Contains a system for self-assignable roles (further referred to as `topics`).


## `?` (list topics)

Lists all available topics.

```css
.?
```


## `+` (assign topics)

Assigns the user the specified topics.

```css
.+ <topics>
```

Arguments:

| Argument | Required                  | Description                                  |
|:--------:|:-------------------------:|:---------------------------------------------|
| `topics` | :fontawesome-solid-check: | One or more topics (separated by `,` or `;`) |


## `-` (unassign topics)

Unassigns the user the specified topics.

```css
.- <topics>
```

Arguments:

| Argument | Required                  | Description                                  |
|:--------:|:-------------------------:|:---------------------------------------------|
| `topics` | :fontawesome-solid-check: | One or more topics (separated by `,` or `;`) |

!!! hint
    You can use `.- *` to remove all topics at once.


## `*` (register topics)

Adds new topics to the list of available topics. For each topic a new role will be created if there is no role with the same name yet (case insensitive).

```css
.* <topics>
```

Arguments:

| Argument | Required                  | Description                                  |
|:--------:|:-------------------------:|:---------------------------------------------|
| `topics` | :fontawesome-solid-check: | One or more topics (separated by `,` or `;`) |

Required Permissions:

- `betheprofessional.manage`


## `/` (delete topics)

Removes topics from the list of available topics and deletes the associated roles.

```css
./ <topics>
```

Arguments:

| Argument | Required                  | Description                                  |
|:--------:|:-------------------------:|:---------------------------------------------|
| `topics` | :fontawesome-solid-check: | One or more topics (separated by `,` or `;`) |

Required Permissions:

- `betheprofessional.manage`


## `%` (unregister topics)

Unregisters topics without deleting the associated roles.

```css
.% <topics>
```

Arguments:

| Argument | Required                  | Description                                  |
|:--------:|:-------------------------:|:---------------------------------------------|
| `topics` | :fontawesome-solid-check: | One or more topics (separated by `,` or `;`) |

Required Permissions:

- `betheprofessional.manage`
