# UserNotes

This cog contains a system for user notes.


## `add`

The `.user_notes add` add a note for a specific user.

```css
.user_notes [add|a|+] <member> <content>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:heavy_check_mark:|A member.| |
|`note`|:heavy_check_mark:|The note you want to add|

Required Permissions:

- `user_notes.read`
- `user_notes.write`


## `remove`

The `.user_notes remove` command remove the user note by note id.

```css
.user_notes [remove|r|delete|d|-] <note_id>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`note_id`|:heavy_check_mark:|A note id. You can see|

Required Permissions:

- `user_notes.read`
- `user_notes.write`


## `show`

The `.user_notes show` command shows all notes of a member.

```css
.user_notes [show|s|list|l] <member>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:heavy_check_mark:|A member.|

Required Permissions:

- `user_notes.read`
