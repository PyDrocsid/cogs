# BeTheProfessional

This cog contains a system for self-assignable topics


## `list_topics`

The `.?` command lists all available topics at the level `parent_topic`.

By default `parent_topic` is the Root Level.

```css
.? [parent_topic]
```

|    Argument    | Required | Description            |
|:--------------:|:--------:|:-----------------------|
| `parent_topic` |          | Parent Level of Topics |


## `assign_topics`

The `.+` command assigns the user the specified topics.


!!! important
    Use only the topic name! Not the Path!

```css
.+ <topic>
```

| Argument |         Required          | Description                                                                    |
|:--------:|:-------------------------:|:-------------------------------------------------------------------------------|
| `topic`  | :fontawesome-solid-check: | A topic name. Multible topics can be added by separating them using `,` or `;` |


## `unassign_topics`

The `.-` command unassigns the user the specified topics.

!!! important
    Use only the topic name! Not the Path!

```css
.- <topic>
```

| Argument |         Required          | Description                                                                       |
|:--------:|:-------------------------:|:----------------------------------------------------------------------------------|
| `topic`  | :fontawesome-solid-check: | A topic name. Multible topics can be removed by separating them using `,` or `;`. |

!!! note
    You can use `.- *` to remove all topics at once.


## `register_topics`

The `.*` command adds new topics to the list of available topics.

!!! note
    You can use a topic's path!

Topic Path Examples:

- `Parent/Child` - Parent must already exist
- `TopLevelNode`
- `Main/Parent/Child2` - Main and Parent must already exist

```css
.* <topic>
```

|   Argument   |         Required          | Description                                                                                  |
|:------------:|:-------------------------:|:---------------------------------------------------------------------------------------------|
|   `topic`    | :fontawesome-solid-check: | The new topic's path. Multible topics can be registered by separating them using `,` or `;`. |
| `assignable` |                           | Asignability of the created topic/topics                                                     |


## `delete_topics`

The `./` command removes topics from the list of available topics and deletes the associated roles.

!!! important
    Use only the topic name! Not the Path!

```css
./ <topic>
```

| Argument |         Required          | Description                                                                       |
|:--------:|:-------------------------:|:----------------------------------------------------------------------------------|
| `topic`  | :fontawesome-solid-check: | A topic name. Multible topics can be deleted by separating them using `,` or `;`. |


## `topic`

The `.topic` command pings all members by topic name.
If a role exists for the topic, it'll ping the role.

If `message` is set, the bot will reply to the given message.

```css
.topic <topic_name> [message]
```

|   Argument   |         Required          | Description                                        |
|:------------:|:-------------------------:|:---------------------------------------------------|
| `topic_name` | :fontawesome-solid-check: | A topic name.                                      |
|  `message`   |                           | A Discord Message. e.g. Message ID or Message Link |


## `btp`

The `.btp` command shows all BTP Settings.
It requires the `betheprofessional.read` Permission.


### `leaderboard`

The `.btp leaderboard` command lists the top `n` topics sorted by users.

```css
.btp [leaderboard|lb] [n]
```

|  Argument   | Required | Description                                                                                                                                    |
|:-----------:|:--------:|:-----------------------------------------------------------------------------------------------------------------------------------------------|
|     `n`     |          | Number of topics shown in the leaderboard. Limited by a Setting. Permission to bypass the Limit `betheprofessional.bypass_leaderboard_n_limit` |
| `use_cache` |          | Disable Cache. Requires the Bypass Permission `betheprofessional.bypass_leaderboard_cache`                                                     |


### `role_limit`

The `.btp role_limit` command is used to change the `role_limit` Settings for BTP.

```css
.btp role_limit <role_limit>
```

|   Argument   |         Required          | Description                 |
|:------------:|:-------------------------:|:----------------------------|
| `role_limit` | :fontawesome-solid-check: | New value of `role_setting` |


### `role_create_min_users`

The `.btp role_create_min_users` command is used to change the `role_create_min_users` Settings for BTP.

```css
.btp role_create_min_users <role_create_min_users>
```

|        Argument         |         Required          | Description                          |
|:-----------------------:|:-------------------------:|:-------------------------------------|
| `role_create_min_users` | :fontawesome-solid-check: | New value of `role_create_min_users` |


### `leaderboard_default_n`

The `.btp leaderboard_default_n` command is used to change the `leaderboard_default_n` Settings for BTP.

```css
.btp leaderboard_default_n <leaderboard_default_n>
```

|        Argument         |         Required          | Description                          |
|:-----------------------:|:-------------------------:|:-------------------------------------|
| `leaderboard_default_n` | :fontawesome-solid-check: | New value of `leaderboard_default_n` |


### `leaderboard_max_n`

The `.btp leaderboard_max_n` command is used to change the `leaderboard_max_n` Settings for BTP.

```css
.btp leaderboard_max_n <leaderboard_max_n>
```

|      Argument       |         Required          | Description                      |
|:-------------------:|:-------------------------:|:---------------------------------|
| `leaderboard_max_n` | :fontawesome-solid-check: | New value of `leaderboard_max_n` |


## `user_topics`

The `usertopics` command is used to show all topics a User has assigned.

```css
.[usertopics|usertopic|utopics|utopic] [member]
```

| Argument | Required | Description                                           |
|:--------:|:--------:|:------------------------------------------------------|
| `member` |          | A member. Default is the Member executing the command |


## `topic_update_roles`

The `.topic_update_roles` manually updates the Top Topics.
The Top Topics will get a Role.
These roles remain even in the case of a rejoin.
It will usually get executed in a 24-hour loop.

```css
.[topic_update_roles|topic_update|update_roles] 
```
