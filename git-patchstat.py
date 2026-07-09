#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

from git import Repo
from datetime import datetime, UTC
import re
import sys
import glob
import json
import os
import hashlib
import argparse
import time
import tempfile
from collections import defaultdict

# ------------------ Constants ------------------------

# Tags to look for in message body. Author is not a tag in the body, it is read from the commit object.
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

# ------------------ Commit indexing (in-memory) ------------------------

def build_commit_index(repo_path, cache):
    """Walk the repo exactly once and return an in-memory list of all commit
    metadata, so that repeated searches (interactive mode) never re-walk git.

    Each element is a tuple of pre-computed, search-ready fields:
        (sha, author_lower, email_lower, email, year, is_merge, message_lower)

    Lower-cased variants are stored so per-search matching is a plain substring
    test with no re-lowercasing. `cache` (the persistent per-sha JSON) is used to
    skip re-parsing commit objects across runs and is augmented with any newly
    seen commits. Returns (index, cache_updated).
    """
    repo = Repo(repo_path)
    commits = list(repo.iter_commits("--all"))
    total_commits = len(commits)
    index = []
    new_entries = 0

    for i, commit in enumerate(commits, 1):
        if i % 1000 == 0 or i == total_commits:
            print(f"\rIndexing commit {i} / {total_commits}", end="", flush=True)
        sha = commit.hexsha
        entry = cache.get(sha)
        # Older caches predate "is_merge"; treat them as incomplete and refresh.
        if entry is None or "is_merge" not in entry:
            entry = {
                "author_name": commit.author.name or "",
                "author_email": commit.author.email or "",
                "message": commit.message,
                "year": datetime.fromtimestamp(commit.committed_date, UTC).year,
                "is_merge": len(commit.parents) > 1,
            }
            cache[sha] = entry
            new_entries += 1
        email = entry["author_email"]
        index.append((
            sha,
            entry["author_name"].lower(),
            email.lower(),
            email,
            entry["year"],
            entry["is_merge"],
            entry["message"].lower(),
        ))
    print()
    return index, new_entries > 0

def _commit_files(repo, sha, memo):
    """Return the list of file paths touched by a commit, memoised per process.

    Only called for the matched author's non-merge commits under -vv, so the
    memo stays small and the expensive per-commit diff runs at most once."""
    if memo is not None and sha in memo:
        return memo[sha]
    files = list(repo.commit(sha).stats.files.keys())
    if memo is not None:
        memo[sha] = files
    return files

# ------------------ Core contribution accounting function ------------------------

def analyze_contributions(name, index, repo=None, stats_memo=None,
                          debug=False, debug_file=None, dir_depth=3, verbosity=0):
    """Search the pre-built in-memory `index` for a developer's contributions.

    Performs no git walking: it iterates the list produced by
    build_commit_index. File-stat lookups (verbosity >= 2) are fetched lazily
    via `repo` and memoised in `stats_memo`.
    """
    name_lower = name.lower()
    contributions = defaultdict(lambda: defaultdict(int))
    all_years = set()
    email_usage = defaultdict(set)
    email_author_counts = defaultdict(int)
    if verbosity >= 2:
        dir_commits = defaultdict(int)
        dir_files = defaultdict(set)
        seen_files = set()
    else:
        dir_commits = {}
        dir_files = {}

    # A tag line can only match if the developer's name appears in the message,
    # so the substring pre-filter in the loop lets us skip these regexes for the
    # vast majority of commits. Patterns run against the lower-cased message.
    tag_patterns = [
        (tag, re.compile(rf"{re.escape(tag.lower())}:\s+.*{re.escape(name_lower)}.*"))
        for tag in LINUX_TAGS
    ]

    for sha, author_lower, email_lower, email, year, is_merge, message_lower in index:
        author_match = name_lower in author_lower or name_lower in email_lower
        name_in_message = name_lower in message_lower
        if not (author_match or name_in_message):
            continue

        tag_match = False
        if author_match:
            if is_merge:
                contributions["Merges"][year] += 1
                email_usage[email].add(year)
                email_author_counts[email] += 1
                continue # merge commits don't count in Author or Sign-offs
            contributions["Author"][year] += 1
            tag_match = True
            email_usage[email].add(year)
            email_author_counts[email] += 1

            if verbosity >= 2:
                try:
                    touched_dirs = set()
                    for path in _commit_files(repo, sha, stats_memo):
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
                        print(f"\n[DEBUG] Could not count directories for commit {sha}: {e}", file=debug_file)

        if name_in_message:
            for tag, pattern in tag_patterns:
                matches = pattern.findall(message_lower)
                if matches:
                    contributions[tag][year] += len(matches)
                    tag_match = True

        if tag_match or author_match:
            all_years.add(year)

    return (contributions, sorted(all_years), email_usage,
            email_author_counts, dir_commits, dir_files)

# ------------------ Parsing MAINTAINERS file ------------------------

def find_community_responsibilities(name, maintainers_path="MAINTAINERS"):
    responsibilities = []
    if not os.path.exists(maintainers_path):
        return responsibilities
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

def count_files_and_lines(file_globs):
    matched_files = set()
    total_lines = 0
    for pattern in file_globs:
        if os.path.isdir(pattern):
            # Recursively walk the directory
            for root, _, files in os.walk(pattern):
                for file in files:
                    file_path = os.path.join(root, file)
                    if file_path not in matched_files:
                        matched_files.add(file_path)
                        try:
                            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                                total_lines += sum(1 for _ in f)
                        except Exception as e:
                            print(f"[WARN] Could not read file {file_path}: {e}")
        else:
            # Try glob matching
            for file_path in glob.glob(pattern, recursive=True):
                if os.path.isfile(file_path) and file_path not in matched_files:
                    matched_files.add(file_path)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            total_lines += sum(1 for _ in f)
                    except Exception as e:
                        print(f"[WARN] Could not read file {file_path}: {e}")
    return len(matched_files), total_lines

def process_block(block, name):
    name_lower = name.lower()
    title = None
    maintainers = []
    reviewers = []
    file_globs = []
    matched_globs = []
    matched_line = None
    role = None
    matched = False
    for line in block:
        if not line.startswith((" ", "\t")) and not title:
            title = line.strip()
        elif line.startswith("M:"):
            maintainer = line[2:].strip()
            maintainers.append(maintainer)
            if name_lower in maintainer.lower() and role is None:
                matched_line = line.strip()
                role = "maintainer"
                matched = True
        elif line.startswith("R:"):
            reviewer = line[2:].strip()
            reviewers.append(reviewer)
            if name_lower in reviewer.lower() and role is None:
                matched_line = line.strip()
                role = "reviewer"
                matched = True
        elif line.startswith("F:"):
            glob_line = line[2:].strip()
            file_globs.append(glob_line)
            if matched:
                matched_globs.append(glob_line)
    if matched_line:
        file_count, line_count = count_files_and_lines(matched_globs)
        return {
            "subsystem": title or "",
            "role": role,
            "matched_line": matched_line,
            "maintainers": maintainers,
            "reviewers": reviewers,
            "files": matched_globs, # Only relevant globs
            "file_count": file_count,
            "line_count": line_count
        }
    return None

# ------------------ Print helper functions ------------------------

def print_community_responsibilities(responsibilities, verbosity):
    maintained = [r for r in responsibilities if r["role"] == "maintainer"]
    reviewed = [r for r in responsibilities if r["role"] == "reviewer"]

    if maintained:
        print("\nMaintainer for:")
        for idx, entry in enumerate(maintained, 1):
            print(f" {idx:>2}. {entry['subsystem'][:50]:<70} ({entry['file_count']:>4} files, {entry['line_count']:>7} lines)")
            if verbosity >= 2 and entry["files"]:
                for f in entry["files"]:
                    print(f"      F: {f}")
    if reviewed:
        print("\nReviewer for:")
        for idx, entry in enumerate(reviewed, 1):
            print(f" {idx:>2}. {entry['subsystem'][:50]:<70} ({entry['file_count']:>4} files, {entry['line_count']:>7} lines)")
            if verbosity >= 2 and entry["files"]:
                for f in entry["files"]:
                    print(f"      F: {f}")

def print_email_summary(email_usage, email_author_counts):
    print("\nEmail usage history:")
    if not email_usage:
        print(" No emails found.")
        return
    max_email_length = max(len(email) for email in email_usage)
    sorted_emails = sorted(email_usage.items(), key=lambda item: min(item[1]))
    for email, year_set in sorted_emails:
        first = min(year_set)
        last = max(year_set)
        count = email_author_counts.get(email, 0)
        print(
            f" [{first} - {last}] {email.ljust(max_email_length)} ({str(count).rjust(4)} commit{'s' if count != 1 else ''})"
        )

def print_top_directories(dir_commits, dir_files, top_limit=5, verbosity=2):
    print("\nTop modified directories (commits and unique files):")
    all_dirs = set(dir_commits) | set(dir_files)
    combined = [
        (dir_name, dir_commits.get(dir_name, 0), len(dir_files.get(dir_name, set())))
        for dir_name in all_dirs
    ]
    if verbosity < 3:
        combined = sorted(combined, key=lambda x: (x[1], x[2]), reverse=True)[:top_limit]
    else:
        combined = sorted(combined, key=lambda x: (x[1], x[2]), reverse=True)
    max_dir_name_len = max(len(d) for d in all_dirs) if all_dirs else 10
    name_col_width = max(max_dir_name_len, 10)
    for dir_name, commits, files in combined:
        print(f" {dir_name:<{name_col_width}} commits: {commits:>4} files: {files:>3}")

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
                dir_commits, dir_files, top_limit=5, verbosity=2, output_path=None):
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

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(json_output, f, indent=2)
        print(f"[INFO] JSON output written to: {output_path}")
    else:
        print(json.dumps(json_output, indent=2))

# ------------------ Shared developer stats routine ------------------------

def process_developer_stats(name, args, index, repo=None, stats_memo=None):
    """
    Unified routine for both interactive and non-interactive modes.
    Handles debug log, contribution analysis, output, and responsibilities.
    Searches the pre-built in-memory `index`; only 'name' varies per invocation.
    """
    debug_file = None
    if args.debug:
        tmpf = tempfile.NamedTemporaryFile(
            mode='w', delete=False,
            prefix="git-patchstat-debug-", suffix=".log"
        )
        debug_file = tmpf
        print(f"[DEBUG] Logging to {debug_file.name}")

    (
        contributions, years,
        email_usage, email_author_counts,
        dir_commits, dir_files
    ) = analyze_contributions(
        name, index, repo=repo, stats_memo=stats_memo,
        debug=args.debug, debug_file=debug_file,
        dir_depth=args.dir_depth, verbosity=args.verbose
    )

    if not years:
        print(f"No contributions found for '{name}'.")
        if debug_file:
            debug_file.close()
        return

    output_path = None
    write_json = args.json or args.json_path is not None
    if write_json:
        if args.json_path and args.json_path != "AUTO":
            output_path = args.json_path
        else:
            tmp_file = tempfile.NamedTemporaryFile(
                mode='w', delete=False,
                suffix=".json", prefix="git-patchstat-", dir="/tmp"
            )
            output_path = tmp_file.name
            tmp_file.close()

    if write_json:
        print_json(
            contributions, name, email_usage, email_author_counts,
            dir_commits, dir_files, top_limit=args.top, verbosity=args.verbose,
            output_path=output_path
        )
    else:
        print_table(
            contributions, years, name, email_usage, email_author_counts,
            dir_commits, dir_files, top_limit=args.top, verbosity=args.verbose
        )

    if args.verbose >= 1:
        maintainers_path = os.path.join(args.repo, "MAINTAINERS")
        if os.path.exists(maintainers_path):
            responsibilities = find_community_responsibilities(name, maintainers_path)
            if responsibilities:
                print_community_responsibilities(responsibilities, args.verbose)
        else:
            print("[INFO] No MAINTAINERS file found in repo.")

    if debug_file:
        debug_file.close()
        print(f"[DEBUG] Debug log written to {debug_file.name}")

# ------------------ Main entry point ------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze git patch contributions for a developer to a git repo.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  git-patchstat.py "Amit Kucheria" # Basic stats
  git-patchstat.py "Amit Kucheria" -v # Include email usage
  git-patchstat.py "Amit Kucheria" -vv # Also include top directories
  git-patchstat.py "Amit Kucheria" -vvv # Show all directories/files
  git-patchstat.py "Amit Kucheria" --json # JSON output
  git-patchstat.py --interactive         # Prompt repeatedly
  git-patchstat.py --repo /path/to/linux --dir-depth 2 --top 10
""")
    parser.add_argument("name", nargs="?", help="Contributor name to search for (omit for --interactive mode)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactive mode: prompt for developer names")
    parser.add_argument("--repo", default=".", help="Path to the Git repo (default: current directory)")
    parser.add_argument("--dir-depth", type=int, default=2, help="Directory depth to track (default: 2)")
    parser.add_argument("--top", type=int, default=5, help="Limit for top directories/files (default: 5)")
    parser.add_argument("--json", action="store_true",
                        help="Enable JSON output (writes to file in /tmp if --json-path not specified)")
    parser.add_argument("--json-path", nargs="?", const="AUTO", default=None,
                        help="Write JSON output to a file. If used without --json, it still saves the file.")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity: -v (email), -vv (dirs), -vvv (everything)")
    parser.add_argument("-d", "--debug", action="store_true", help="Print debug timing info")

    args = parser.parse_args()

    # Build the in-memory commit index exactly once. Every subsequent search
    # (especially in interactive mode) runs purely against this list with no
    # further git walking, so repeated lookups are near-instant.
    cache = load_cache(args.repo)
    index, cache_updated = build_commit_index(args.repo, cache)
    if cache_updated:
        save_cache(args.repo, cache)
    # Shared repo handle + per-process memo for lazy file-stat lookups (-vv).
    repo = Repo(args.repo)
    stats_memo = {}

    if args.interactive:
        print("\nInteractive mode: type developer names to get stats. Type 'exit' or blank to quit.\n")
        try:
            while True:
                name = input("Enter developer name (or 'exit' to quit): ").strip()
                if not name or name.lower() == "exit":
                    print("Exiting interactive mode.")
                    break
                process_developer_stats(name, args, index, repo=repo, stats_memo=stats_memo)
                if not (args.json or args.json_path is not None):
                    input("Press SPACE and Enter to continue, or Ctrl+C to exit... ")
        except KeyboardInterrupt:
            print("\nExiting interactive mode.")
            sys.exit(0)
        sys.exit(0)

    # --- Non-interactive mode ---
    if not args.name:
        print("Error: You must either provide a developer name or use --interactive mode.")
        sys.exit(1)
    process_developer_stats(args.name, args, index, repo=repo, stats_memo=stats_memo)

if __name__ == "__main__":
    main()
