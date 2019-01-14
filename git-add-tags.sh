#!/bin/bash

# Add review tags to a patch series.

# This only works for the entire range of SHAs specified on the
# commandline, so if you have acks on only a part of the series, it might
# be necessary to split them up into smaller ranges

STR=${1:?"Usage: $0 <str> <start SHA-1> [end SHA]"}
START_SHA=${2:?"Usage: $0 <str> <start SHA-1> [end SHA]"}
#END_SHA=${3:-HEAD}

echo "WARNING! This is a destructive operation that could wreck your branch. Do it on a temporary branch first"
echo "The command to be run is:"
echo ""
echo "     git filter-branch -f --msg-filter \"cat && echo \"$STR\"\" $START_SHA..HEAD"

read -p "* Press 'y' to continue: " REPLY
[ "$REPLY" == "y" ] || exit

git filter-branch -f --msg-filter "cat && echo \"$STR\"" $START_SHA..HEAD

