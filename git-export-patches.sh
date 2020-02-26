#!/bin/bash

# Script to dump patches into work/patches from git that are appropriately
# titled and threaded

CURR_BRANCH=`git rev-parse --abbrev-ref HEAD`
SHA=${1:?"Usage: $0 <shaid> <str> [topic]"}
STR=${2:?"Usage: $0 <shaid> <str> [topic]"}
TOPIC=${3:-$CURR_BRANCH}

DUMPDIR=~/work/patches/`basename $TOPIC`

if [ -d $DUMPDIR ]; then
	read -e -p "$DUMPDIR exists, overwrite? (N/y)"
	if [ "$REPLY" == "y" ]; then
		rm -rf `readlink -e $DUMPDIR`
		mkdir -p $DUMPDIR
	else
		echo "Exiting (specify another topic name to prevent overwriting existing patches)"
		exit
	fi
fi
echo "Exporting patches to $DUMPDIR"

num=$(git patchnum $SHA | wc -l)

# For a single patch, no cover-letter, no patch numbers
# For upto 2 patches, no cover-letter
# For > 2 patches, cover letter, patch numbers
if [ $num -eq 1 ]; then
	git format-patch -N -M --subject-prefix="$STR" $SHA -o $DUMPDIR
elif [ $num -eq 2 ]; then
	git format-patch -M --subject-prefix="$STR" $SHA -o $DUMPDIR
else
	git format-patch -M --subject-prefix="$STR" --cover-letter $SHA -o $DUMPDIR
fi

echo "Running checkpatch"
./scripts/checkpatch.pl  --strict --patch $DUMPDIR/*.patch

