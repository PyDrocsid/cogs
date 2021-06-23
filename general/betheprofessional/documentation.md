# BeTheProfessional

This cog contains a system for self-assignable roles (further referred to as `topics`).

## `list_topics`
The `.?` command lists all available topics.

```css
.?
```

## `assign_topics`
The `.+` command assigns the user the specified topics.

```css
.+ <topic>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`topic`|:heavy_check_mark:|A topic. Multible topics can be added by separating them using `,` or `;`|


## `unassign_topics`
The `.-` command unassigns the user the specified topics.

```css
.- <topic>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`topic`|:heavy_check_mark:|A topic. Multible topics can be removed by separating them using `,` or `;`.|

!!! note
    You can use `.- *` to remove all topics at once.


## `register_topics`
The `.*` command adds new topics to the list of available topics.

```css
.* <topic>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`topic`|:heavy_check_mark:|The new topic's name. If no role with this name (case insensitive) exists, one is created. Multible topics can be registered by separating them using `,` or `;`.|

## `delete_topics`
The `./` command removes topics from the list of available topics and deletes the associated roles.

```css
./ <topic>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`topic`|:heavy_check_mark:|A topic. Multible topics can be deleted by separating them using `,` or `;`.|


## `unregister_topics`
The `.%` command unregisters topics without deleting the associated roles.

```css
.% <topic>
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`topic`|:heavy_check_mark:|A topic. Multible topics can be unregistered by separating them using `,` or `;`.|
