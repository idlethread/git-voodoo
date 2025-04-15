#!/bin/bash

# Download series using b4 and apply to current branch

MSGID=${1:?"Usage: $0 <msg-id>"}

b4 am -o ~/work/patches/__incoming/ -n foo -c $MSGID
# Save a copy of the mailbox with a unique name
b4 am -o ~/work/patches/__incoming/ -c $MSGID

git am ~/work/patches/__incoming/foo.mbx


# Get a diff stat of all the files that were touched with this patch series and run a check on them

#LASTAG=`git describe --tags --abbrev=0`
#paste -s <(git diff --dirstat=lines,0 $LASTAG.. | cut -d'%' -f2)
