# PubSub Channels

This is a list of all global PubSub channels. For a more detailed explanation on how these PubSub channels work, please refer to the [PubSub documentation](/library/pubsub).


## `send_to_changelog`

Use this PubSub channel to send a message to a server's changelog channel.

```python
async def send_to_changelog(guild: Guild, message: Union[str, Embed]) -> []
```

Arguments:

- `guild`: The server the changelog entry should be sent to
- `message`: The changelog entry (text or embed)

Returns: `None`

Subscriptions:

- [Logging](/cogs/moderation/logging)


## `send_alert`

Use this PubSub channel to send a message to a server's internal alert channel.

```python
async def send_alert(guild: Guild, message: Union[str, Embed]) -> []
```

Arguments:

- `guild`: The server the message should be sent to
- `message`: The message to be sent (text or embed)

Returns: `None`

Subscriptions:

- [Logging](/cogs/moderation/logging)


## `log_auto_kick`

Use this PubSub channel to log an automatic member kick.

```python
async def log_auto_kick(member: Member) -> []
```

Arguments:

- `member`: The member that was kicked

Returns: `None`

Subscriptions:

- [Mod Tools](/cogs/moderation/mod)


## `get_user_info_entries`

Use this PubSub channel to get/provide information about a user for the user info command (e.g. statistics for mutes and bans).

```python
async def get_user_info_entries(user_id: int) -> list[list[tuple[str, str]]]
```

Arguments:

- `user_id`: The user id

Returns: A list of `(name, value)` tuples

Subscriptions:

- [Mod Tools](/cogs/moderation/mod)


## `get_user_status_entries`

Use this PubSub channel to get/provide status information about a user for the user info command (e.g. current membership status or inactivity information).

```python
async def get_user_status_entries(user_id: int) -> list[list[tuple[str, str]]]
```

Arguments:

- `user_id`: The user id

Returns: A list of `(name, value)` tuples

Subscriptions:

- [Inactivity](/cogs/information/inactivity)
- [Mod Tools](/cogs/moderation/mod)


## `get_userlog_entries`

Use this PubSub channel to get/provide log entries about a user for the user log command.

```python
async def get_userlog_entries(user_id: int, author: Member) -> list[list[tuple[datetime, str]]]
```

Arguments:

- `user_id`: The user id
- `author`: The member who asked fot the userlogs

Returns: A list of `(datetime, log_entry)` tuples

Subscriptions:

- [Invite Whitelist](/cogs/moderation/invites)
- [MediaOnly](/cogs/moderation/mediaonly)
- [Mod Tools](/cogs/moderation/mod)
- [User Notes](/cogs/moderation/user_notes)
- [Content Filter](/cogs/moderation/content_filter)


## `revoke_verification`

Use this PubSub channel to revoke a member's verification.

```python
async def revoke_verification(member: Member) -> []
```

Arguments:

- `member`: The member

Returns: `None`

Subscriptions:

- [User Info](/cogs/information/user_info)


## `can_respond_on_reaction`

Use this PubSub channel to find out whether a cog is allowed to send a message into a channel in response to a reaction.

```python
async def can_respond_on_reaction(channel: TextChannel) -> list[bool]
```

Arguments:

- `channel`: The text channel

Returns: `True` if it is ok to send a message into this channel, `False` otherwise

Subscriptions:

- [Logging](/cogs/moderation/logging)
- [MediaOnly](/cogs/moderation/mediaonly)


## `ignore_message_edit`

Use this PubSub channel to prevent the next edit event of a message from being logged.

```python
async def ignore_message_edit(message: Message) -> []
```

Arguments:

- `message`: The message

Returns: `None`

Subscriptions:

- [Logging](/cogs/moderation/logging)
