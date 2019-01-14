#! /bin/bash
#
# git-smart-cc - send cover letter to all mailing lists referenced in a
# patch series intended to be used as 'git send-email --cc-cmd=git-smart-cc
# ...' done by Wolfram Sang in 2012-14, version 20140204 - WTFPLv2
#
# Modified to use CCLIST for hardcoded list of receipients - Amit

#opts="--nogit-fallback --norolestats --pattern-depth=1"
#cover_opts="--no-m"
cover_opts=""
#patch_opts="--nol"
patch_opts=""

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
