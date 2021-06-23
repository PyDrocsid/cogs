# User Info

This cog contains commands to show information about Discord user accounts.

## `user`
The `.user` command shows general information about the requested user.

```css
.[userinfo|user|uinfo|userstats] [user]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`||The user whose information is requested. If omitted, the requesting user receives their own information as a direct message.|

!!! note
    - Every user is allowed to request their own information.
    - Requesting other users' information, however, requires the `user_info.view_userinfo` permission.

The user information given by this command includes:

- Current username, discriminator, avatar and id
- Moderation statistics:
    - Reports
    - Warns
    - Mutes
    - Kicks
    - Bans
- Membership status
- User activity
- Active punishments

!!! note
    Moderation statistics:

    - The term `active` refers to the number of times this user *has actively* reported/punished someone else.
    - The term `passive` refers to the number of times this user *has been* reported/punished e.g. by a moderator.


## `joined`
The `.joined` command shows a rough estimate of how much time has passed since the last verification of a given member. If no `Verified` role has been configured yet, this estimate refers to the last join date of this member.

```css
.joined [member]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`member`||The member whose information is requested. If omitted, this defaults to the requesting member.|


## `ulog`
The `.ulog` command shows the moderation log of a given user.

```css
.[userlogs|userlog|ulog] [user]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`user`||The user whose log is requested. If omitted, the requesting user receives their own log as a direct message.|

!!! note
    - Every user is allowed to request their own moderation log.
    - Requesting other users' logs, however, requires the `user_info.view_userlog` permission.

The user log given by this command contains the following events:

- Account creation
- Guild joins and leaves
- Username and nickname changes
- Verification state changes
- Discord invite approvals and removals
- Passive moderation actions:
    - Reports
    - Warns
    - Mutes
    - Kicks
    - Bans


## `init_join_log`
The `.init_join_log` command creates join (and, if enabled, verification) log entries for every user based on their [join dates received from the Discord API](https://discordpy.readthedocs.io/en/latest/api.html#discord.Member.joined_at){target=_blank}, if those entries don't already exist.

```.css
.init_join_log
```

!!! note
    - This command requires the `user_info.init_join_log` permission. It is recommended to grant this permission only to administrators.
    - As the bot has to individually create log entries in the database for every user, execution of this command may take a while.
