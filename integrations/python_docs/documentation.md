# Python Documentation

This cog contains commands to access and search the documentation of [Python](https://docs.python.org/3/){target=_blank} and [pycord](https://docs.pycord.dev/en/master/){target=_blank}. When using these commands to search for Python entities (e.g. functions, classes, objects, modules), the documentation is downloaded into the Redis cache to avoid repetitive queries.


## `python_docs`

Use this command to search the [Python documentation](https://docs.python.org/3/){target=_blank} for any Python entity:

```css
,[python_docs|py] [entity]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`entity`||The name of the Python entity to search for|

If you don't provide an `entity`, you get the direct link to the [Python documentation](https://docs.python.org/3/){target=_blank} instead.


## `pycord_docs`

Use this command to search the [pycord documentation](https://docs.pycord.dev/en/master/){target=_blank} for any discord.py entity:

```css
,[pycord_docs|pycord|pyc|dpy] [entity]
```

|Argument|Required|Description|
|:------:|:------:|:----------|
|`entity`||The name of the discord.py entity to search for|

If you don't provide an `entity`, you get the direct link to the [pycord documentation](https://docs.pycord.dev/en/master/){target=_blank} instead.
