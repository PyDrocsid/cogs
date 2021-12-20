# User Notes

This cog provides the `.user_notes` command to manage user notes.


## `user_notes`

The `.user_notes` command contains subcommands to manage user notes.

```css
.[user_notes|un]
```

Required Permissions:

- `user_notes.read`


### `show`

The `show` subcommand shows all notes of a specific user.

```css
.user_notes [show|s|list|l] <member>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:fontawesome-solid-check:|A member|

Required Permissions:

- `user_notes.read`


### `add`

The `add` subcommand is used to add a note to a specific user.

```css
.user_notes [add|a|+] <member> <content>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:fontawesome-solid-check:|A member|
|`content`|:fontawesome-solid-check:|The note you want to add|

Required Permissions:

- `user_notes.read`
- `user_notes.write`


### `remove`

The `remove` subcommand removes a user note by note id.

```css
.user_notes [remove|r|delete|d|-] <note_id>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`note_id`|:fontawesome-solid-check:|A note id|

Required Permissions:

- `user_notes.read`
- `user_notes.write`
