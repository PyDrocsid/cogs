#!/bin/bash

repo=$(mktemp -d)
git clone --recursive https://github.com/PyDrocsid/documentation.git $repo
rm -rf $repo/cogs
mkdir $repo/cogs
cp -r * $repo/cogs/
pushd $repo

./pages_build.sh

popd
mv $repo/site .
rm -rf $repo
