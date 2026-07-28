import os
import re
from pathlib import Path
import csv
import re


def template_to_regex(template):
    """
    Convert pattern like *_*_(dddd_dddd/dddd-dddd)_* to regex.
    Supports:
      - d     → digit
      - *     → any characters
      - (a/b) → alternation, e.g. (dddd_dddd/dddd-dddd)
    """
    def part_to_regex(part):
        if re.fullmatch(r'd+', part):
            return rf'(\d{{{len(part)}}})'
        elif part == '*':
            return r'[^_]*'   # ← was r'(?:.*)' — now stops at underscore
        else:
            return re.escape(part)

    def expand_alternation(group):
        """Convert (dddd_dddd/dddd-dddd) to (?:regex1|regex2)"""
        options = group.split('/')
        regex_options = []
        for option in options:
            # split by _ or - keeping separators
            tokens = re.split(r'([_\-])', option)
            regex_option = ''.join(
                part_to_regex(t) if t not in ('_', '-') else re.escape(t)
                for t in tokens
            )
            regex_options.append(regex_option)
        return f'(?:{"|".join(regex_options)})'

    # Split on _ only outside parentheses
    parts = []
    current = ''
    depth = 0
    for char in template:
        if char == '(':
            depth += 1
            current += char
        elif char == ')':
            depth -= 1
            current += char
        elif char == '_' and depth == 0:
            parts.append(current)
            current = ''
        else:
            current += char
    if current:
        parts.append(current)

    # Convert each part to regex
    regex_parts = []
    for part in parts:
        if part.startswith('(') and part.endswith(')'):
            regex_parts.append(expand_alternation(part[1:-1]))
        else:
            regex_parts.append(part_to_regex(part))

    return '_'.join(regex_parts)


def extract_key(filename, regex):
    # Remove all extensions (handles .copc.laz etc.)
    stem = filename
    while True:
        root, ext = os.path.splitext(stem)
        if not ext:
            break
        stem = root
    match = regex.search(stem)
    if match:
        return "_".join([x for x in match.groups() if x])
    return None


def index_folder(folder, regex):
    index = {}
    for f in Path(folder).iterdir():
        if f.is_file():
            key = extract_key(f.name, regex)
            if key:
                index[key] = f.name
    return index


def preprocess_into_csv(src_folder_old, src_folder_new, src_res, output_csv, pattern_template, verbose=False):
    # --------------------------------
    # SETTINGS
    # --------------------------------

    # Pattern: *_*_dddd_dddd_* → captures the two 4-digit codes as the matching key
    # d = digit, * = anything
    # pattern_template = "*_*_dddd_dddd_*"

    regex_str = template_to_regex(pattern_template)
    regex = re.compile(regex_str, re.IGNORECASE)

    index1 = index_folder(src_folder_old, regex)
    index2 = index_folder(src_folder_new, regex)

    # --------------------------------
    # Match pairs
    # --------------------------------
    all_keys = set(index1.keys()) | set(index2.keys())

    matched = []
    unmatched1 = []
    unmatched2 = []

    for key in sorted(all_keys):
        f1 = index1.get(key)
        f2 = index2.get(key)
        if f1 and f2:
            matched.append((key, f1, f2))
        elif f1:
            unmatched1.append((key, f1))
        else:
            unmatched2.append((key, f2))

    # --------------------------------
    # Write CSV
    # --------------------------------
    src_res = os.path.join(os.path.dirname(src_folder_old), 'results') if src_res == 'default' else src_res
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        writer.writerow(['key', 'pc1', 'pc2', 'res', 'status'])
        for key, f1, f2 in matched:
            writer.writerow([key, f1, f2, os.path.join(src_res, f'{key}_res'), 'matched'])
        for key, f1 in unmatched1:
            writer.writerow([key, f1, '', '', 'no_pc2'])
        for key, f2 in unmatched2:
            writer.writerow([key, '', f2, '', 'no_pc1'])

    # --------------------------------
    # Summary
    # --------------------------------
    if verbose:
        print(f"Matched pairs : {len(matched)}")
        print(f"Only in folder1: {len(unmatched1)}")
        print(f"Only in folder2: {len(unmatched2)}")
        if unmatched1:
            print("\nNo match in folder2:")
            for key, f in unmatched1:
                print(f"  [{key}] {f}")
        if unmatched2:
            print("\nNo match in folder1:")
            for key, f in unmatched2:
                print(f"  [{key}] {f}")
