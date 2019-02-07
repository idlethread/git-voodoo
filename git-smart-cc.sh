#! /bin/bash
#
# git-smart-cc
#
# 1. send cover letter to everyone (people and mailing lists) referenced in
# a patch series
# 2. Be smart about who to put in TO and who in CC for each patch in the
# series
#
# Intended to be used as 'git send-email --cc-cmd=git-smart-cc ...'
# done by Wolfram Sang in 2012-14, version 20140204 - WTFPLv2
#
# Modified to use CCLIST for hardcoded list of receipients - Amit

progname=$(basename "$0")
#echo $progname

if [ "$progname" = "git-smart-cc.sh" ]; then
	cover_opts="--nogit --nogit-fallback --norolestats --l --nom"
	patch_opts="--nogit --nogit-fallback --norolestats --l --nom"
elif  [ "$progname" = "git-smart-to.sh" ]; then
	cover_opts="--nogit --nogit-fallback --norolestats --m --r --nol --pattern-depth=1"
	patch_opts="--nogit --nogit-fallback --norolestats --m --r --nol --pattern-depth=1"
fi

shopt -s extglob
dir=${1%/*}
if [ -e $dir/CCLIST ]; then
#	echo "Found CCList"
	cat $dir/CCLIST
fi
cd $(git rev-parse --show-toplevel) > /dev/null

if [ ! -x scripts/get_maintainer.pl ]; then
	exit 0
fi

# Split patch number and name
name=${1##*/}
num=${name%%-*}

#echo "$name, $num"

if [ "$num" = "0000" ]; then
	for f in $dir/!(0000*).patch; do
		scripts/get_maintainer.pl $cover_opts $f
	done | sort -u
else
	scripts/get_maintainer.pl $patch_opts $1
fi
