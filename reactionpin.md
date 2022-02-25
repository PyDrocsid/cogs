# Reaction Pin


This cog consists of a reaction event and some moderation commands.


## Reaction Pin


A message gets pinned when

a)
the user who added the reaction `:pushpin` (📌) has the `reactionpin.pin` permission OR

b)

1.`:pushpin:` (📌) is added as a reaction to a message AND

2. the reaction is added by the author of the message AND

3. the message was written in a channel whitelisted for ReactionPin AND

4. the user does not have the `mute` role


As soon as the message author or a Team-Member removes his reaction `:pushpin:` 📌, the message will be removed from the pinned messages.

---
## `reactionpin`  


This is the main command for the command group, to show all the subcommands if you have permission for it.


Required Permissions:

- `reactionpin.read`


Aliases:

- `a`


```css  
.reactionpin <command>
```


---

### `add`


This command whitelists a channel.

Required Permissions:

- `reactionpin.read`
- `reactionpin.write`


Aliases:

- `add`
- `a`
- `+`


```css  
.rp [add|a|+] <channel>
```

| Arguments | Required | Description            |
|:---------:|:---------|:-----------------------|
| `channel` | ✔️       | Whitelists the channel |


---

### `remove`


This command removes a channel from the whitelist.

Required Permissions:

- `reactionpin.read`
- `reactionpin.write`


Aliases

- `remove`

- `del`

- `r`

- `d`

- `-`


```css  
.rp [del|r|d|-] <channel>
```

|Arguments|Required|Description|
|:------:|:-----|:-----|
|`channel`|✔️|Removes the channel from the whitelist|  

---

### `pin_message`


This command enables or disables the "MorpheusHelper pinned a message. See all messages" message.

[![image](https://www.linkpicture.com/q/Screenshot-2021-10-17-072804_1.png)](https://www.linkpicture.com/view.php?img=LPic616bc85447a64587571420)


Required Permissions:

- `reactionpin.read`

- `reactionpin.write`


Aliases:

- `pm`


```css  
.rp [pin_message|pm] <enabled>
```

Arguments:

|Argument|Required|Description|
|:------:|:----|:------:|
|enabled|✔️|Message is displayed if true|  
