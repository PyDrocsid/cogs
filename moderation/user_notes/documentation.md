# user_notes

The `.user_notes` command contains subcommands to manage user notes.

```css
.[user_notes|un] [subcommand]
```


### `add`

The `add` subcommand is used to add a note to a specific user.

```css
.user_notes [add|a|+] <member> <content>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:heavy_check_mark:|A member|
|`note`|:heavy_check_mark:|The note you want to add|

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
|`note_id`|:heavy_check_mark:|A note id|

Required Permissions:

- `user_notes.read`
- `user_notes.write`


### `show`

The `show` subcommand shows all notes for a member.

```css
.user_notes [show|s|list|l] <member>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:heavy_check_mark:|A member|

Required Permissions:

- `user_notes.read`
