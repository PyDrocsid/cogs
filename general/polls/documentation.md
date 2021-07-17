# Polls

This cog provides commands for simple "yes/no" polls, multiple choice polls and team polls.


## `yesno`

The `.yesno` command creates a "yes/no" poll by putting :thumbsup: and :thumbsdown: as reactions under the message (pictures and other files work, too).

```css
.[yesno|yn] [content]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`content`|       |The message content / A message link|

If `content` is a message link, the bot puts the reactions on the message this link refers to.


## `poll`

The `.poll` command creates a poll with 1 to a maximum of 19 options.

```css
.[poll|vote] <question>
[emoji1] <option1>
[emojiX] [optionX]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`question`|:heavy_check_mark:|The poll topic/question|
|`emojiX`|       |The reaction emote for option X|
|`option1`|:heavy_check_mark:|The first poll option|
|`optionX`|       |The Xth poll option|

!!! note
    Multiline titles and options can be specified using a \ at the end of a line


## `teampoll`

The `.teampoll` command creates a poll with 1 to a maximum of 20 options and shows which team members have not voted yet.

```css
.[teampoll|teamvote|tp] <question>
[emoji1] <option1>
[emojiX] [optionX]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`question`|:heavy_check_mark:|The poll topic/question|
|`emojiX`|       |The reaction emote for option X|
|`option1`|:heavy_check_mark:|The first poll option|
|`optionX`|       |The Xth poll option|

!!! note
    Multiline titles and options can be specified using a \ at the end of a line
