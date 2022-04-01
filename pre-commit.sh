#!/bin/bash

# install via ./pre-commit.sh install

if [[ "$1" = "install" ]]; then
    hooks=$(git rev-parse --git-path hooks)
    rm -f $hooks/pre-commit
    ln -s $(realpath --relative-to $hooks pre-commit.sh) $hooks/pre-commit
    exit 0
fi

git diff > unstaged.patch
git apply --allow-empty -R unstaged.patch

$HOME/.local/bin/poe pre-commit
code=$?

git add -u
git apply --allow-empty unstaged.patch && rm unstaged.patch

exit $code
