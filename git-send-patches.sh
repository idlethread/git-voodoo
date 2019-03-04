#!/bin/sh

# Use git send-email to send a series of patches exported through the
# export-patches.sh script

MYTO=${1:?"Usage: $0 <to> <dir> <--internal>"}
MYDIR=${2:?"Usage: $0 <to> <dir> <--internal>"}
INTERNAL_ONLY=${3:-""}

if [ "${INTERNAL_ONLY}" = "--internal" ]; then
	git -c sendemail.tocmd=true send-email --suppress-cc=all --dry-run --to "$MYTO" "$MYDIR"/*.patch
else
	git send-email --dry-run --to "$MYTO" "$MYDIR"/*.patch
fi

echo "Checklist:"
echo "1. Test the patches"
echo "2. Update the cover letter"

echo "If you're happy with the result of the command, copy-paste the
following line and remove dry-run to actually send email"
if [ "${INTERNAL_ONLY}" = "--internal" ]; then
	echo "git -c sendemail.tocmd=true send-email --suppress-cc=all --to "$MYTO" "$MYDIR"/*.patch"
else
	echo "git send-email --to $MYTO $MYDIR/*.patch"
fi
