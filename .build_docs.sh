#!/bin/sh

git clone https://github.com/PyDrocsid/documentation.git
cd documentation
rmdir cogs
ln -s .. cogs
./build.sh
