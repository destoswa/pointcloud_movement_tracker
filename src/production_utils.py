import os
import re
from pathlib import Path

# --------------------------------
# Convert pattern template to regex
# --------------------------------
# def template_to_regex(template):
#     """Convert pattern like *_*_dddd_dddd_* to a regex with a capture group"""
#     # Escape dots, then replace 'd' groups with \d{n} and '*' with .*
#     parts = template.split("_")
#     regex_parts = []
#     key_group_indices = []
#     for i, part in enumerate(parts):
#         if re.fullmatch(r'd+', part):
#             # This is a digit group → part of the matching key
#             regex_parts.append(rf'(\d{{{len(part)}}})')
#             key_group_indices.append(i)
#         elif part == '*':
#             regex_parts.append(r'[^_]+')
#         else:
#             regex_parts.append(re.escape(part))
#     return '_'.join(regex_parts), key_group_indices


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


# --------------------------------
# Extract key from filename
# --------------------------------
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

# --------------------------------
# Index files in each folder
# --------------------------------
def index_folder(folder, regex):
    index = {}
    for f in Path(folder).iterdir():
        if f.is_file():
            key = extract_key(f.name, regex)
            if key:
                index[key] = f.name
    return index