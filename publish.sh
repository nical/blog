#!/bin/sh

echo "building..." &&
pelican ./content -s ./publishconf.py &&
echo "copying into nical.github.io..." &&
cp -r ./output/* ../nical.github.io/ &&
echo "git add . && git commit -am $1" &&
cd ../nical.github.io/ &&
git add . &&
git commit -am "$1" &&
echo "Blog updated, push nical.github.io to publish the modifications online."
