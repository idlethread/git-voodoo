#!/bin/bash
# set -ax

by_name() {
    git log --date=iso -i --grep="$1" | tr -s ' ' ' ' | awk --posix -F ':' -v name="$1" '
	$1~/^Date/  { split($2, dt, "-");  }
	$1~/^Author/ && $2~name  { author++; authyr[dt[1]]++ }
	$1~/Signed-off-by/ && $2~name  { signed++; signyr[dt[1]]++; }
	$1~/Acked-by/ && $2~name  { acked++; ackyr[dt[1]]++; }
	$1~/Cc/ && $2~name  { cc++; ccyr[dt[1]]++; }
	$1~/Reviewed-by/ && $2~name  { reviewed++; reviewyr[dt[1]]++; }
	$1~/Reported-by/ && $2~name  { reported++; reportyr[dt[1]]++; }
	$1~/Tested-by/ && $2~name  { tested++; testyr[dt[1]]++; }
	END {
		printf "Author:\t\t%s\t ||", author+0
		for (year in authyr)
			printf "%s: %s\t", year, authyr[year]
		printf "\nSigned-off-by:\t%s\t ||", signed+0
		for (year in signyr)
			printf "%s: %s\t", year, signyr[year]
		printf "\nAcked-by:\t%s\t ||", acked+0
		for (year in ackyr)
			printf "%s: %s\t", year, ackyr[year]
		printf "\nReviewed-by\t%s\t ||", reviewed+0
		for (year in reviewyr)
			printf "%s: %s\t", year, reviewyr[year]
		printf "\nReported-by\t%s\t ||", reported+0
		for (year in reportyr)
			printf "%s: %s\t", year, reportyr[year]
		printf "\nTested-by\t%s\t ||", tested+0
		for (year in testyr)
			printf "%s: %s\t", year, testyr[year]
		printf "\nCc\t\t%s\t ||", cc+0
		for (year in ccyr)
			printf "%s: %s\t", year, ccyr[year]
		printf "\n"
	}'
}

by_all() {
    git log | tr -s ' ' ' ' | awk -F '[:>]' '
$1~/Author/  { name[$2]++; author[$2]++; }
$1~/Signed-off-by/ {  name[$2]++; signed[$2]++ }
$1~/Acked-by/ {  name[$2]++; acked[$2]++ }
$1~/Cc/ {  name[$2]++; cc[$2]++ }
$1~/Reviewed-by/ {  name[$2]++; reviewed[$2]++ }
$1~/Reported-by/ {  name[$2]++; reported[$2]++ }
$1~/Tested-by/ {  name[$2]++; tested[$2]++ }
END {
	for (i in name) {
        	printf("%s Author:%s>\n", author[i]+0, i)
                printf("%s Signed-off-by:%s>\n", signed[i]+0, i)
                printf("%s Acked-by:%s>\n", acked[i]+0, i)
                printf("%s Reviewed-by:%s>\n", reviewed[i]+0, i)
                printf("%s Reported-by:%s>\n", reported[i]+0, i)
                printf("%s Tested-by:%s>\n", tested[i]+0, i)
                printf("%s Cc:%s>\n", cc[i]+0, i)
                printf("%s Total:%s>\n", name[i]+0, i)
        }
}'
}

if [ "$#" = "0" ]; then
    by_all
else
    by_name "$1"
fi
