#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

from git import Repo
from datetime import datetime, UTC
import re
import sys
import json
import os
import hashlib
import argparse
import time
import tempfile
from collections import defaultdict

# ------------------ Constants ------------------------

# Tags to look for in message body, Author is not a tag in the body, it is read from the commit object
LINUX_TAGS = [
    "Signed-off-by", "Acked-by", "Reviewed-by",
    "Reported-by", "Tested-by", "Cc", "Co-developed-by"
]

# Order in which to display contributions
DISPLAY_TAGS = [
    "Author",
    "Co-developed-by",
    "Signed-off-by",
    "Acked-by",
    "Reviewed-by",
    "Reported-by",
    "Tested-by",
    "Cc",
    "Merges"
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
    print(f"\n[INFO] Saving cache to {path}... Please do not interrupt.")
    with open(path, "w") as f:
        json.dump(cache, f)

# ------------------ Commit metadata extraction ------------------------

def get_commit_metadata(commit, cache, new_cache):
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

    return sha, entry["author_name"], entry["author_email"], entry["message"], entry["year"]

# ------------------ Core contribution accounting function ------------------------

def parse_git_commits(name, repo_path=".", cache=None, debug=False, debug_file=None, dir_depth=3, verbosity=0):
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

        tag_match = False

        sha, author, email, message, year = get_commit_metadata(commit, cache, new_cache)
        author_match = name_lower in author.lower() or name_lower in email.lower()

        if author_match:
            if len(commit.parents) > 1:
                contributions["Merges"][year] += 1
                email_usage[email].add(year)
                email_author_counts[email] += 1
                continue              # merge commits don't count in Author or Sign-offs

            contributions["Author"][year] += 1
            tag_match = True
            email_usage[email].add(year)
            email_author_counts[email] += 1

            if verbosity >= 2:
                try:
                    stats = commit.stats.files
                    touched_dirs = set()
                    for path in stats:
                        # Show full path (minus filename) if path less that dir_depth, else truncate
                        parts = path.split("/")
                        dirs = parts[:-1]
                        depth = min(len(dirs), dir_depth)
                        top_dir = "/".join(dirs[:depth]) if dirs else "."
                        touched_dirs.add(top_dir)
                        if path not in seen_files:
                            if debug:
                                print(f"email: {email[:30]:<30} file: {path[:55]:<55} sha: {sha[:15]:<15}", file=debug_file)
                            dir_files[top_dir].add(path)
                            seen_files.add(path)
                    for top_dir in touched_dirs:
                        dir_commits[top_dir] += 1
                except Exception as e:
                    if debug:
                        print(f"\n[DEBUG] Could not count directories for commit {sha}: {e}")

        for tag in LINUX_TAGS:
            pattern = rf"{tag}:\s+.*{re.escape(name)}.*"
            matches = re.findall(pattern, message, re.IGNORECASE)
            if matches:
                contributions[tag][year] += len(matches)
                tag_match = True

        if tag_match or author_match:
            all_years.add(year)
            if min_year is None or year < min_year:
                min_year = year

    print()
    cache.update(new_cache)

    dir_files_count = {k: len(v) for k, v in dir_files.items()} if verbosity >= 2 else {}

    return (contributions, min_year, sorted(all_years),
            email_usage, email_author_counts,
            dir_commits, dir_files, bool(new_cache))

# ------------------ Parsing MAINTAINERS file  ------------------------

def find_community_responsibilities(name, maintainers_path="MAINTAINERS"):
    responsibilities = []

    with open(maintainers_path, "r", encoding="utf-8") as f:
        block = []
        for line in f:
            if line.strip() == "":
                subsystem_info = process_block(block, name)
                if subsystem_info:
                    responsibilities.append(subsystem_info)
                block = []
            else:
                block.append(line)
        if block:
            subsystem_info = process_block(block, name)
            if subsystem_info:
                responsibilities.append(subsystem_info)

    return responsibilities

def process_block(block, name):
    name_lower = name.lower()
    title = None
    maintainers = []
    reviewers = []
    file_globs = []

    matched_line = None
    role = None

    for line in block:
        if not line.startswith((" ", "\t")) and not title:
            title = line.strip()
        elif line.startswith("M:"):
            maintainers.append(line[2:].strip())
            if name_lower in line.lower():
                matched_line = line.strip()
                role = "maintainer"
        elif line.startswith("R:"):
            reviewers.append(line[2:].strip())
            if name_lower in line.lower():
                matched_line = line.strip()
                role = "reviewer" if role != "maintainer" else "both"
        elif line.startswith("F:"):
            file_globs.append(line[2:].strip())

    if matched_line:
        return {
            "subsystem": title or "<unknown>",
            "role": role,
            "matched_line": matched_line,
            "maintainers": maintainers,
            "reviewers": reviewers,
            "files": file_globs,
        }

    return None

# ------------------ Print helper functions ------------------------

def print_community_responsibilities(responsibilities, verbosity):
    maintained = [r for r in responsibilities if r["role"] in ("maintainer", "both")]
    reviewed = [r for r in responsibilities if r["role"] in ("reviewer", "both")]

    if maintained:
        print("\nMaintainer for:")
        for idx, entry in enumerate(maintained, 1):
            print(f" {idx:>2}. {entry['subsystem']}")
            if verbosity >= 2 and entry["files"]:
                for f in entry["files"]:
                    print(f"     F: {f}")

    if reviewed:
        print("\nReviewer for:")
        for idx, entry in enumerate(reviewed, 1):
            print(f" {idx:>2}. {entry['subsystem']}")
            if verbosity >= 2 and entry["files"]:
                for f in entry["files"]:
                    print(f"     F: {f}")

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
        (
            dir_name,
            dir_commits.get(dir_name, 0),
            len(dir_files.get(dir_name, set()))
        )
        for dir_name in all_dirs
    ]

    if verbosity < 3:
        combined = sorted(combined, key=lambda x: (x[1], x[2]), reverse=True)[:top_limit]
    else:
        combined = sorted(combined, key=lambda x: (x[1], x[2]), reverse=True)

    # Determine dynamic width for dir_name column
    max_dir_name_len = max(len(d) for d in all_dirs)
    name_col_width = max(max_dir_name_len, 10)  # Minimum padding for aesthetics

    for dir_name, commits, files in combined:
        print(f"  {dir_name:<{name_col_width}}  commits: {commits:>4}  files: {files:>3}")


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

def print_json(contributions, name, email_usage, email_author_counts,
               dir_commits, dir_files, top_limit=5, verbosity=2):
    json_output = {
        "name": name,
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

    if dir_commits or dir_files:
        all_dirs = set(dir_commits) | set(dir_files)

        combined = [
            {
                "directory": d,
                "commits": dir_commits.get(d, 0),
                "files_changed": len(dir_files.get(d, set()))
            }
            for d in all_dirs
        ]

        combined = sorted(combined, key=lambda x: (x["commits"], x["files_changed"]), reverse=True)

        if verbosity < 3:
            combined = combined[:top_limit]

        json_output["directories"] = combined

    print(json.dumps(json_output, indent=2))

# ------------------ Main entry point ------------------------

def main():
    debug_log = None
    parser = argparse.ArgumentParser(
        description="Analyze git patch contributions for a developer to a git repo.",
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

    if args.debug:
        debug_log = tempfile.NamedTemporaryFile(mode='w', delete=False, prefix="git-patchstat-debug-", suffix=".log")
        print(f"[DEBUG] Logging to {debug_log.name}")

    (contributions, min_year, years,
     email_usage, email_author_counts,
     dir_commits, dir_files, cache_updated) = parse_git_commits(
         args.name, args.repo, cache=cache,
         debug=args.debug, debug_file=debug_log, dir_depth=args.dir_depth,
         verbosity=args.verbose
     )
    t2 = time.time()

    if not years:
        print(f"No contributions found for '{args.name}'.")
        return

    if args.json:
        print_json(contributions, args.name, email_usage, email_author_counts,
                   dir_commits, dir_files, args.top, args.verbose)

    print_table(contributions, years, args.name,
                email_usage, email_author_counts,
                dir_commits, dir_files,
                top_limit=args.top, verbosity=args.verbose)

    if args.verbose >= 1:
        maintainers_path = os.path.join(args.repo, "MAINTAINERS")
        if os.path.exists(maintainers_path):
            responsibilities = find_community_responsibilities(args.name, maintainers_path)
            if responsibilities:
                print_community_responsibilities(responsibilities, args.verbose)
        else:
            print("[INFO] No MAINTAINERS file found in repo.")

    if cache_updated:
        save_cache(args.repo, cache)
    t3 = time.time()

    if args.debug:
        print("\n[DEBUG] Execution time breakdown:")
        print(f"  Load cache:        {t1 - t0:.2f} s", file=debug_log)
        print(f"  Analyze commits:   {t2 - t1:.2f} s", file=debug_log)
        print(f"  Save cache:        {t3 - t2:.2f} s", file=debug_log)
        print(f"  Total:             {t3 - t0:.2f} s", file=debug_log)
        if debug_log:
            debug_log.close()
            print(f"[DEBUG] Debug log written to {debug_log.name}")

if __name__ == "__main__":
    main()
