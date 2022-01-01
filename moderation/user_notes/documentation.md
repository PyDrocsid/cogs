# User Notes

Contains the `.user_notes` command to manage user notes.


## `user_notes`

Contains subcommands to manage user notes.

```css
.[user_notes|un]
```

Required Permissions:

- `user_notes.read`


### `show`

Shows all notes for a specific user.

```css
.user_notes [show|s|list|l] <user>
```

Arguments:

| Argument | Required                  | Description |
|:--------:|:-------------------------:|:------------|
| `user`   | :fontawesome-solid-check: | A user      |

Required Permissions:

- `user_notes.read`


### `add`

Adds a note to a specific user.

```css
.user_notes [add|a|+] <user> <content>
```

Arguments:

| Argument  | Required                  | Description     |
|:---------:|:-------------------------:|:----------------|
| `user`    | :fontawesome-solid-check: | A user          |
| `content` | :fontawesome-solid-check: | The note to add |

Required Permissions:

- `user_notes.read`
- `user_notes.write`


### `remove`

Removes a user note by note id.

```css
.user_notes [remove|r|delete|d|-] <note_id>
```

Arguments:

| Argument  | Required                  | Description |
|:---------:|:-------------------------:|:------------|
| `note_id` | :fontawesome-solid-check: | A note id   |

Required Permissions:

- `user_notes.read`
- `user_notes.write`
