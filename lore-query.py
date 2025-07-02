#!/bin/env python

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlencode
import re
import csv
import argparse
import sys


def search_patch(subject: str, author: str):
    query = f's:"{subject}" AND f:"{author}"'
    params = {"q": query, "x": "A"}
    search_url = "https://lore.kernel.org/all/?" + urlencode(params)

    headers = {
        "User-Agent": "Lynx/2.8.8dev.3 libwww-FM/2.14 SSL-MM/1.4.1"
    }

    try:
        response = requests.get(search_url, headers=headers)
    except requests.RequestException:
        return None, None

    if response.status_code != 200:
        return None, None

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return None, None

    namespace = {'atom': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('atom:entry', namespace)

    if not entries:
        return None, None

    matches = []
    for entry in entries:
        title = entry.find('atom:title', namespace).text.strip()

        if title.lower().startswith("re:"):
            continue
        if subject.lower() not in title.lower():
            continue

        link = entry.find('atom:link', namespace).attrib['href']
        date_str = entry.find('atom:updated', namespace).text
        try:
            date = datetime.fromisoformat(date_str.rstrip("Z"))
        except Exception:
            date = date_str

        matches.append({
            'title': title,
            'url': link,
            'date': date,
        })

    if not matches:
        return None, None

    matches.sort(key=lambda x: x['date'], reverse=True)
    latest = matches[0]
    return latest['url'], latest['date']


def process_file(file_path: str, output_csv: str = None):
    results = []

    known_prefixes = ["FROMLIST", "QCLINUX", "UPSTREAM", "PENDING"]
    prefix_pattern = re.compile(rf'^({"|".join(known_prefixes)}):\s*', re.IGNORECASE)

    with open(file_path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            match = re.match(r'"(.*?)"\s+"(.*?)"', line)
            if not match:
                print(f"[Line {lineno}] Skipping invalid line: {line}", file=sys.stderr)
                continue

            author, raw_subject = match.groups()

            # Detect and strip known prefix
            prefix_match = prefix_pattern.match(raw_subject)
            prefix = prefix_match.group(1).upper() if prefix_match else "-"
            subject = prefix_pattern.sub('', raw_subject)

            url, date = search_patch(subject, author)

            if url:
                date_str = date.date().isoformat() if isinstance(date, datetime) else str(date).split("T")[0]
                print(f'{author},{subject},{prefix},{url},{date_str}')
                results.append((author, subject, prefix, url, date_str))
            else:
                print(f'{author},{subject},{prefix},Not found,-')
                results.append((author, subject, prefix, "Not found", "-"))

    if output_csv:
        with open(output_csv, "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["Author", "Subject", "Prefix", "URL", "Date"])
            writer.writerows(results)
        print(f"\nResults written to: {output_csv}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Search patches on lore.kernel.org by subject and author"
    )
    parser.add_argument(
        "input_file", help='Input text file with lines like: "author" "subject"'
    )
    parser.add_argument(
        "--output", "-o", help="Optional output CSV file", default=None
    )
    args = parser.parse_args()

    process_file(args.input_file, args.output)


if __name__ == "__main__":
    main()
