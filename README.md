# Patch handling


 * git-export-patches.sh: Export the patches

   $ `git export-patches.sh HEAD~7 "PATCH v1"`

 * git-send-patches.sh: Send the patch already exported after editing the
   cover-letter and amending a CCLIST file

   $ `git send-patches.sh linux-kernel@vger.kernel.org ~/work/patches/sdm845-thermal-throttling-v1/`

 * git-smart-cc.sh: Script to be a little smart about who to cc on a patch.
   It uses the contents of the CCLIST file (if present) and then uses
   get_maintainer.pl. Automatically used by git-send-patches.sh

# Dealing with Reviews

 * git-add-tags.sh: Add review tags to a set of commits

   $ `git-add-tags "Reviewed-by: Foo Bar <foo@bar.org>" 34abcd34`


# Miscellaneous

 * git-patchstat.sh: Show patch statistics for a developer. Useful
   pre-interview check :-)

   $ `git-patchstat.sh "Amit Kucheria"`

