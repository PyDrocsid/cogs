# UserNotes

This cog contains a system for user notes.


## `add`

The `.user_notes add` command adds a note for a specific user.

```css
.user_notes [add|a|+] <member> <content>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:heavy_check_mark:|A member| |
|`note`|:heavy_check_mark:|The note you want to add|

Required permissions:

- `user_notes.read`
- `user_notes.write`


## `remove`

The `.user_notes remove` command removes the user note by note id.

```css
.user_notes [remove|r|delete|d|-] <note_id>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`note_id`|:heavy_check_mark:|A note id You can see|

Required permissions:

- `user_notes.read`
- `user_notes.write`


## `show`

The `.user_notes show` command shows all notes belonging to a member.

```css
.user_notes [show|s|list|l] <member>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:heavy_check_mark:|A member|

Required permissions:

- `user_notes.read`
