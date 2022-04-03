# Python Documentation

Contains commands to access and search the documentation of [Python](https://docs.python.org/3/){target=_blank} and [pycord](https://docs.pycord.dev/en/master/){target=_blank}. When using these commands to search for Python entities (e.g. functions, classes, objects, modules), the documentation is downloaded into the Redis cache to avoid repetitive queries.


## `python_docs`

Searches the [Python documentation](https://docs.python.org/3/){target=_blank} for any Python entity.

```css
.[python_docs|py] [entity]
```

Arguments:

| Argument | Required |Description                                                                                                            |
|:--------:|:--------:|:----------------------------------------------------------------------------------------------------------------------|
| `entity` |          | The name of the Python entity to search for. If omitted, you get the direct link to the Python documentation instead. |


## `pycord_docs`

Searches the [pycord documentation](https://docs.pycord.dev/en/master/){target=_blank} for any pycord entity.

```css
.[pycord_docs|pycord|pyc|dpy] [entity]
```

Arguments:

| Argument | Required | Description                                                                                                           |
|:--------:|:--------:|:----------------------------------------------------------------------------------------------------------------------|
| `entity` |          | The name of the pycord entity to search for. If omitted, you get the direct link to the pycord documentation instead. |
