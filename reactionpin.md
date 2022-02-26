# Reaction Pin


This cog consists of a reaction event and some moderation commands.


## Reaction Pin


A message gets pinned when

a)
the user who added the reaction `:pushpin` (📌) has the `reactionpin.pin` permission OR

b)

1. `:pushpin:` (📌) is added as a reaction to a message AND

2. the reaction is added by the author of the message AND

3. the message was written in a channel whitelisted for ReactionPin AND

4. the user does not have the `mute` role


As soon as the message author or a Team-Member removes his reaction `:pushpin:` 📌, the message will be removed from the pinned messages.

---


## `reactionpin`  


This is the main command for the command group, to show all the subcommands if you have permission for it.




Aliases:

- `a`


```css  
.reactionpin <command>
```

Required Permissions:

- `reactionpin.read`


---


### `add`


This command whitelists a channel.



```css  
.rp [add|a|+] <channel>
```

| Arguments | Required | Description            |
|:---------:|:---------|:-----------------------|
| `channel` | ✔️       | Whitelists the channel |

Aliases:

- `add`
- `a`
- `+`


Required Permissions:

- `reactionpin.read`
- `reactionpin.write`

---


### `remove`


This command removes a channel from the whitelist.


```css  
.rp [del|r|d|-] <channel>
```

|Arguments|Required|Description|
|:------:|:-----|:-----|
|`channel`|✔️|Removes the channel from the whitelist|  


Aliases

- `remove`

- `del`

- `r`

- `d`

- `-`


Required Permissions:

- `reactionpin.read`
- `reactionpin.write`


---


### `pin_message`

This command enables or disables the "pinned messages notification".

[![image](https://www.linkpicture.com/q/Screenshot-2021-10-17-072804_1.png)](https://www.linkpicture.com/view.php?img=LPic616bc85447a64587571420)



```css  
.rp [pin_message|pm] <enabled>
```

Arguments:

|Argument|Required|Description|
|:------:|:----|:------:|
|enabled|✔️|Message is displayed if true|  


Aliases:

- `pm`



Required Permissions:

- `reactionpin.read`

- `reactionpin.write`
