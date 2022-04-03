# Bot Info

Contains information about the bot and its tasks.


## `info`

Shows information about the bot.

```css
.[info|infos|about]
```

The information given by this command includes:

- Bot name and description
- Author
- Contributors
- Version
- Number of enabled cogs
- Github repository
- PyDrocsid [Discord](../../../discord){target=_blank} and [GitHub](https://github.com/PyDrocsid){target=_blank} links
- Prefix
- Help command
- Where to submit bug reports and feature requests


## `version`

Returns the bot's current version.

```css
.[version|v]
```


## `github`

Returns information about the bot's GitHub repository.

```css
.[github|gh]
```


## `contributors`

Returns a list of all people that contributed to the bot.

```css
.[contributors|contri|con]
```


## `cogs`

Returns a list of all cogs currently in use.

```css
.cogs
```


## Status Message

The bot displays a status message that is updated every 20 seconds. The list of status strings is defined under the `profile_status` [translation key](../../../library/translations/){target=_blank}.
