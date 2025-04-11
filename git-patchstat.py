#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# MIT License
#
# Copyright (c) 2020-2024 Amit Kucheria
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# git-patchstat.py - Git patch statistics utility

from git import Repo
from datetime import datetime, UTC
import re
import sys
import json
import os
import hashlib
import argparse
import time
from collections import defaultdict

# ------------------ Constants ------------------------

LINUX_TAGS = [
    "Signed-off-by", "Acked-by", "Reviewed-by",
    "Reported-by", "Tested-by", "Cc", "Co-developed-by"
]

DISPLAY_TAGS = [
    "Author",
    "Co-developed-by",
    "Signed-off-by",
    "Acked-by",
    "Reviewed-by",
    "Reported-by",
    "Tested-by",
    "Cc"
]

# ------------------ Cache helper functions ------------------------

def get_cache_path(repo_path):
    abs_path = os.path.abspath(repo_path)
    path_hash = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()
    config_dir = os.path.join(os.path.expanduser("~"), ".config", "git-patchstat")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, f"{path_hash}.json")

def load_cache(repo_path):
    path = get_cache_path(repo_path)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_cache(repo_path, cache):
    path = get_cache_path(repo_path)
    with open(path, "w") as f:
        json.dump(cache, f)

# ------------------ Core contribution accounting function ------------------------

def parse_git_commits(name, repo_path=".", cache=None, debug=False, dir_depth=2, verbosity=0):
    repo = Repo(repo_path)
    commits = list(repo.iter_commits("--all"))
    total_commits = len(commits)

    new_cache = {}
    contributions = defaultdict(lambda: defaultdict(int))
    all_years = set()
    min_year = None
    email_usage = defaultdict(set)
    email_author_counts = defaultdict(int)

    if verbosity >= 2:
        dir_commits = defaultdict(int)
        dir_files = defaultdict(set)
        seen_files = set()
    else:
        dir_commits = {}
        dir_files = {}

    name_lower = name.lower()

    for i, commit in enumerate(commits, 1):
        print(f"\rReading commit {i} / {total_commits}", end="", flush=True)

        sha = commit.hexsha

        if sha in cache:
            entry = cache[sha]
        else:
            author = commit.author.name or ""
            email = commit.author.email or ""
            message = commit.message
            year = datetime.fromtimestamp(commit.committed_date, UTC).year

            entry = {
                "author_name": author,
                "author_email": email,
                "message": message,
                "year": year
            }
            new_cache[sha] = entry

        year = entry["year"]
        author = entry["author_name"]
        email = entry["author_email"]
        message = entry["message"]

        matched = False
        author_match = name_lower in author.lower() or name_lower in email.lower()

        if author_match:
            contributions["Author"][year] += 1
            matched = True
            email_usage[email].add(year)
            email_author_counts[email] += 1

        for tag in LINUX_TAGS:
            pattern = rf"{tag}:\s+.*{re.escape(name)}.*"
            matches = re.findall(pattern, message, re.IGNORECASE)
            if matches:
                contributions[tag][year] += len(matches)
                matched = True

        if matched:
            all_years.add(year)
            if min_year is None or year < min_year:
                min_year = year

        if author_match and verbosity >= 2:
            try:
                stats = commit.stats.files
                touched_dirs = set()
                for path in stats:
                    parts = path.split("/")
                    top_dir = "/".join(parts[:dir_depth]) if len(parts) >= dir_depth else path
                    touched_dirs.add(top_dir)
                    if path not in seen_files:
                        dir_files[top_dir].add(path)
                        seen_files.add(path)
                for top_dir in touched_dirs:
                    dir_commits[top_dir] += 1
            except Exception as e:
                if debug:
                    print(f"\n[DEBUG] Could not count directories for commit {sha}: {e}")

    print()
    cache.update(new_cache)

    dir_files_count = {k: len(v) for k, v in dir_files.items()} if verbosity >= 2 else {}

    return (contributions, min_year, sorted(all_years),
            email_usage, email_author_counts,
            dir_commits, dir_files_count)

# ------------------ Print helper functions ------------------------

def print_email_summary(email_usage, email_author_counts):
    print("\nEmail usage history:")
    max_email_length = max(len(email) for email in email_usage)
    sorted_emails = sorted(email_usage.items(), key=lambda item: min(item[1]))
    for email, year_set in sorted_emails:
        first = min(year_set)
        last = max(year_set)
        count = email_author_counts.get(email, 0)
        print(
            f"  [{first} - {last}]  {email.ljust(max_email_length)}  ({str(count).rjust(4)} commit{'s' if count != 1 else ''})"
        )

def print_top_directories(dir_commits, dir_files, top_limit=5, verbosity=2):
    print("\nTop modified directories (commits and unique files):")
    all_dirs = set(dir_commits) | set(dir_files)

    combined = [
        (dir_name, dir_commits.get(dir_name, 0), dir_files.get(dir_name, 0))
        for dir_name in all_dirs
    ]

    if verbosity < 3:
        combined = sorted(combined, key=lambda x: (x[1], x[2]), reverse=True)[:top_limit]
    else:
        combined = sorted(combined, key=lambda x: (x[1], x[2]), reverse=True)

    for dir_name, commits, files in combined:
        print(f"  {dir_name:<30} commits: {commits:<4}  files: {files}")

def print_table(contributions, years, name,
                email_usage, email_author_counts,
                dir_commits, dir_files,
                top_limit=5, verbosity=0):

    if years:
        title = f"Contributions by {name} ({years[0]} - {years[-1]})"
    else:
        title = f"Contributions by {name}"

    print(f"\n{title}")
    print(f"{'Tag':<15} {'Total':>6} | " + " ".join(f"{year:>6}" for year in years))
    print("-" * (15 + 6 + 3 + 7 * len(years)))

    for tag in DISPLAY_TAGS:
        total = sum(contributions[tag].values())
        year_data = " ".join(f"{contributions[tag].get(year, 0):>6}" for year in years)
        print(f"{tag:<15} {total:>6} | {year_data}")

    if verbosity >= 1:
        print_email_summary(email_usage, email_author_counts)
    if verbosity >= 2:
        print_top_directories(dir_commits, dir_files, top_limit, verbosity)

def print_json(contributions, email_usage, email_author_counts,
               dir_commits, dir_files, top_limit=5, verbosity=2):
    json_output = {
        "contributions": {
            tag: dict(sorted(years.items()))
            for tag, years in contributions.items()
            if years
        },
        "email_usage": []
    }

    sorted_emails = sorted(email_usage.items(), key=lambda item: min(item[1]))
    for email, year_set in sorted_emails:
        json_output["email_usage"].append({
            "email": email,
            "first_year": min(year_set),
            "last_year": max(year_set),
            "author_commits": email_author_counts.get(email, 0)
        })

    if dir_commits:
        dirs_sorted = sorted(dir_commits.items(), key=lambda x: x[1], reverse=True)
        if verbosity < 3:
            dirs_sorted = dirs_sorted[:top_limit]
        json_output["directories_by_commit"] = [
            {"directory": d, "commits": count} for d, count in dirs_sorted
        ]

    if dir_files:
        files_sorted = sorted(dir_files.items(), key=lambda x: x[1], reverse=True)
        if verbosity < 3:
            files_sorted = files_sorted[:top_limit]
        json_output["directories_by_files"] = [
            {"directory": d, "files_changed": count} for d, count in files_sorted
        ]

    print(json.dumps(json_output, indent=2))

# ------------------ Main entry point ------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze Git patch contributions for a specific contributor using GitPython.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  git-patchstat.py "Amit Kucheria"            # Basic stats
  git-patchstat.py "Amit Kucheria" -v         # Include email usage
  git-patchstat.py "Amit Kucheria" -vv        # Also include top directories
  git-patchstat.py "Amit Kucheria" -vvv       # Show all directories/files
  git-patchstat.py "Amit Kucheria" --json     # JSON output
  git-patchstat.py "Amit Kucheria" --repo /path/to/linux --dir-depth 2 --top 10
"""
    )

    parser.add_argument("name", help="Contributor name to search for")
    parser.add_argument("--repo", default=".", help="Path to the Git repo (default: current directory)")
    parser.add_argument("--dir-depth", type=int, default=2, help="Directory depth to track (default: 2)")
    parser.add_argument("--top", type=int, default=5, help="Limit for top directories/files (default: 5)")
    parser.add_argument("--json", action="store_true", help="Print results in JSON format")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity: -v (email), -vv (dirs), -vvv (everything)")
    parser.add_argument("-d", "--debug", action="store_true", help="Print debug timing info")

    args = parser.parse_args()

    t0 = time.time()
    cache = load_cache(args.repo)
    t1 = time.time()

    (contributions, min_year, years,
     email_usage, email_author_counts,
     dir_commits, dir_files) = parse_git_commits(
        args.name, args.repo, cache=cache,
        debug=args.debug, dir_depth=args.dir_depth,
        verbosity=args.verbose
    )
    t2 = time.time()

    if not years:
        print(f"No contributions found for '{args.name}'.")
        return

    if args.json:
        print_json(contributions, email_usage, email_author_counts,
                   dir_commits, dir_files, args.top, args.verbose)
    else:
        print_table(contributions, years, args.name,
                    email_usage, email_author_counts,
                    dir_commits, dir_files,
                    top_limit=args.top, verbosity=args.verbose)

    save_cache(args.repo, cache)
    t3 = time.time()

    if args.debug:
        print("\n[DEBUG] Execution time breakdown:")
        print(f"  Load cache:        {t1 - t0:.2f} s")
        print(f"  Analyze commits:   {t2 - t1:.2f} s")
        print(f"  Save cache:        {t3 - t2:.2f} s")
        print(f"  Total:             {t3 - t0:.2f} s")

if __name__ == "__main__":
    main()
