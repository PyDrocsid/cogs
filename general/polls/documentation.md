# Polls

Contains commands for simple "yes/no" polls, multiple choice polls and team polls.


## `yesno`

Creates a "yes/no" poll by adding :thumbsup: and :thumbsdown: reactions to the message (pictures and other files work, too). You can also specify a different message to which the reactions should be added.

```css
.[yesno|yn] [content|message]
```

Arguments:

| Argument  | Required | Description                     |
|:---------:|:--------:|:--------------------------------|
| `content` |          | The message content             |
| `message` |          | The link to a different message |


## `poll`

Creates a poll with 1 to a maximum of 19 options.

```css
.[poll|vote] <question>
[emoji1] <option1>
[emojiX] [optionX]
```

Arguments:

| Argument   | Required                  | Description                     |
|:----------:|:-------------------------:|:--------------------------------|
| `question` | :fontawesome-solid-check: | The poll topic/question         |
| `emojiX`   |                           | The reaction emote for option X |
| `option1`  | :fontawesome-solid-check: | The first poll option           |
| `optionX`  |                           | The Xth poll option             |

!!! info
    Multiline titles and options can be specified using a \ at the end of a line


## `team_yesno`

Creates a "yes/no" poll and shows which team members have not voted yet.

```css
.[team_yesno|tyn] <text>
```

Arguments:

| Argument | Required                  | Description             |
|:--------:|:-------------------------:|:------------------------|
| `text`   | :fontawesome-solid-check: | The poll topic/question |

Required Permissions:

- `polls.team_poll`


## `teampoll`

Creates a poll with 1 to a maximum of 20 options and shows which team members have not voted yet.

```css
.[teampoll|teamvote|tp] <question>
[emoji1] <option1>
[emojiX] [optionX]
```

Arguments:

| Argument   | Required                  | Description                     |
|:----------:|:-------------------------:|:--------------------------------|
| `question` | :fontawesome-solid-check: | The poll topic/question         |
| `emojiX`   |                           | The reaction emote for option X |
| `option1`  | :fontawesome-solid-check: | The first poll option           |
| `optionX`  |                           | The Xth poll option             |

Required Permissions:

- `polls.team_poll`

!!! info
    Multiline titles and options can be specified using a \ at the end of a line
