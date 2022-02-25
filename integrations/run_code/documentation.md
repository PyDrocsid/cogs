# Run Code

Contains commands to run code using the [Piston API](https://github.com/engineer-man/piston){target=_blank}.


## `run`

Executes code using the [Piston API](https://github.com/engineer-man/piston){target=_blank}.

````css
.run ```<language>
<your code>
```
[stdin]
````

Arguments:

|  Argument   | Required                  | Description                                       |
|:-----------:|:-------------------------:|:--------------------------------------------------|
| `language`  | :fontawesome-solid-check: | The language to use for execution                 |
| `your code` | :fontawesome-solid-check: | The code you want to execute                      |
| `stdin`     |                           | The text to pass as standard input to the program |

!!! info
    You can use the [`/runtimes`](https://emkc.org/api/v2/piston/runtimes){target=_blank} endpoint to get a list of all supported programming languages. This list is also shown in the help embed of the `run` command (`.help run`).


## `eval`

Evaluates a Python expression using the [Piston API](https://github.com/engineer-man/piston){target=_blank}.

```css
.[eval|=] <expr>
```

Arguments:

| Argument | Required                  | Description                       |
|:--------:|:-------------------------:|:----------------------------------|
| `expr`   | :fontawesome-solid-check: | The Python expression to evaluate |
