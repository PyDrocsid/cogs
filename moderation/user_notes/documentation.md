# UserNotes

This cog contains a system for user notes.


## `add`

The `.un add` add a note for a specific user.

```css
.?.user_notes [add|a|+] <member> <content>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:heavy_check_mark:|A member. Referenced by ID or `@<username>` |
|`note`|:heavy_check_mark:|The note you want to add|



## `remove`

The `.un remove` command remove the user note by note id.

```css
.user_notes [remove|r|delete|d|-] <note_id>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`note_id`|:heavy_check_mark:|A note id. You can see|


## `show`

The `.un show` command shows all notes of a member.

```css
.user_notes [show|s|list|l] <member>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`|:heavy_check_mark:|A member. Referenced by ID or `@<username>`|