# Mod Tools

This cog contains commands for server moderation purposes.

## `report`

The .report command can be used to report misbehaviour of other server members.

```css
.report <user> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user who should be reported|
|`reason`|:heavy_check_mark:|A description of the users misbehaviour|

The reason cannot be longer than 900 characters.

## `warn`

The .warn command can be used to warn a member because of his misbehaviour.

```css
.warn <user> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user who should be warned|
|`reason`|:heavy_check_mark:|A reason why the user is warned|

The reason cannot be longer than 900 characters.


## `edit_warn`

The .edit_warn command can be used to edit a warns reason.

```css
.[edit_warn|warn_edit] <warn_id> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The id of the warn whose reason should be changed|
|`reason`|:heavy_check_mark:|The new warn reason|

You can obtain the warn id from a users user log.
The reason cannot be longer than 900 characters.
To perform these changes, you need to be the moderator who created the original warn, have a higher moderation level or be the server owner.

## `delete_warn`

The .delete_warn command can be used to delete warns from the database.

```css
.[delete_warn|warn_delete] <warn_id>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The id of the warn which should be deleted|

You can obtain the warn id from a users user log.
To perform these changes, you need to be the moderator who created the original warn, have a higher moderation level or be the server owner.

## `mute`

The .mute command can be used to give a member a formerly configured mute role.

```css
.mute <user> <time> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user who should be warned|
|`time`|:heavy_check_mark:|How long the user should be muted|
|`reason`|:heavy_check_mark:|A reason why the user is muted|

The time must be provided as `[years]y[months]m[weeks]w[days]d[hours]h[minutes]n`, but any time unit that is not required can be ignored.
Set the duration to `inf` to mute a user permanently.
The reason cannot be longer than 900 characters.

## `edit_mute`

The edit_mute command can be used to edit a mute. There are two subcommands:

### `reason`

You can edit a mute reason by using:

```css
.[edit_mute|mute_edit] [reason|r] <mute_id> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`mute_id`|:heavy_check_mark:|The id of the mute whose reason should be changed|
|`reason`|:heavy_check_mark:|The new mute reason|

You can obtain the mute id from a users user log.
To perform these changes, you need to be the moderator who created the original mute, have a higher moderation level or be the server owner.
The reason cannot be longer than 900 characters.

### `duration`

You can edit a mute duration by using:

```css
.[edit_mute|mute_edit] [duration|d] <user> <time>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user whose mute duration should be changed|
|`time`|:heavy_check_mark:|The new mute duration|

The time format required is the same as before.
To perform these changes, you need to be the moderator who created the original mute, have a higher moderation level or be the server owner.
You can only edit the duration of active mutes.

## `delete_mute`

The .delete_mute command can be used to delete a mute from the database.

```css
.[delete_mute|mute_delete] <mute_id>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`mute_id`|:heavy_check_mark:|The id of the mute which should be deleted|

You can obtain a mute id from a users user log.
To perform these changes, you need to be the moderator who created the mute, have a higher moderation level or be the server owner.
If the mute id is linked to an active mute, the mute role will be removed from the user.

## `unmute`

The .unmute command can be used to unmute a user.

```css
.unmute <user> <reason
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user who should be unmuted|
|`reason`|:heavy_check_mark:|The reason why the user should be unmuted|

To perform these changes, you need to be the moderator who created the mute, have a higher moderation level or be the server owner.
The mute role will be removed from the user instantly.

## `kick`

The .kick command can be used to kick a user from the server.

```css
.kick <user> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user who should be kicked|
|`reason`|:heavy_check_mark:|A reason why the user is kicked|

The reason cannot be longer than 900 characters.


## `edit_kick`

The .edit_kick command can be used to edit a kick reason.

```css
.[edit_kick|kick_edit] <kick_id> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`kick_id`|:heavy_check_mark:|The id of the kick whose reason should be changed|
|`reason`|:heavy_check_mark:|The new kick reason|

You can obtain the kick id from a users user log.
The reason cannot be longer than 900 characters.
To perform these changes, you need to be the moderator who created the original kick, have a higher moderation level or be the server owner.

## `delete_kick`

The .delete_kick command can be used to delete warns from the database.

```css
.[delete_kick|kick_delete] <kick_id>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The id of the kick which should be deleted|

You can obtain the kick id from a users user log.
To perform these changes, you need to be the moderator who created the original kick, have a higher moderation level or be the server owner.

## `ban`

The .ban command can be used to ban a user from the server.

```css
.ban <user> <time> <delete_days> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user who should be banned|
|`time`|:heavy_check_mark:|How long the user should be banned|
|`delete_days`|:heavy_check_mark:|How many days in the past messages of the user should be deleted|
|`reason`|:heavy_check_mark:|A reason why the user is banned|

The time must be provided as `[years]y[months]m[weeks]w[days]d[hours]h[minutes]n`, but any time unit that is not required can be ignored.
Set the duration to `inf` to ban a user permanently.
The amount of delete days must be between zero and seven.
The reason cannot be longer than 900 characters.

## `edit_ban`

The .edit_ban command can be used to edit a ban. There are two subcommands:

### `reason`

You can edit a ban reason by using:

```css
.[edit_ban|ban_edit] [reason|r] <ban_id> <reason>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`ban_id`|:heavy_check_mark:|The id of the ban whose reason should be changed|
|`reason`|:heavy_check_mark:|The new ban reason|

You can obtain the ban id from a users user log.
To perform these changes, you need to be the moderator who created the original ban, have a higher moderation level or be the server owner.
The reason cannot be longer than 900 characters.

### `duration`

You can edit a ban duration by using:

```css
.[edit_ban|ban_edit] [duration|d] <user> <time>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user whose ban duration should be changed|
|`time`|:heavy_check_mark:|The new ban duration|

The time format required is the same as before.
To perform these changes, you need to be the moderator who created the original ban, have a higher moderation level or be the server owner.
You can only edit the duration of active bans.

## `delete_ban`

The .delete_ban command can be used to delete a ban from the database.

```css
.[delete_ban|ban_delete] <ban_id>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`ban_id`|:heavy_check_mark:|The id of the ban which should be deleted|

You can obtain a ban id from a users user log.
To perform these changes, you need to be the moderator who created the ban, have a higher moderation level or be the server owner.
If the ban id is linked to an active ban, the user will be unbanned.

## `unban`

The .unban command can be used to unban a user.

```css
.unban <user> <reason
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`|:heavy_check_mark:|The user who should be unbanned|
|`reason`|:heavy_check_mark:|The reason why the user should be unbanned|

To perform these changes, you need to be the moderator who created the ban, have a higher moderation level or be the server owner.
The user will be unbanned instantly.
