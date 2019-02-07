#!/bin/sh

# Use git send-email to send a series of patches exported through the
# export-patches.sh script

MYTO=${1:?"Usage: $0 <to> <dir>"}
MYDIR=${2:?"Usage: $0 <to> <dir>"}


#git send-email --to $MYTO --cc-cmd ~/bin/git-getcc.sh \
#	--envelope-sender $MYFROM --smtp-server $MYSMTP \
#	--suppress-cc=author --suppress-cc=self \
#	$MYDIR/00*.patch

git send-email --dry-run --to "$MYTO" "$MYDIR"/*.patch

echo "Checklist:"
echo "1. Test the patches"
echo "2. Update the cover letter"

echo "If you're happy with the result of the command, copy-paste the
following line and remove dry-run to actually send email"
echo "git send-email --to $MYTO $MYDIR/*.patch"
