import os
import re
from pathlib import Path
import csv
import pandas as pd
import geopandas as gpd
from tqdm import tqdm
from omegaconf import OmegaConf


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
    src_res = os.path.join(os.path.dirname(src_folder_old), 'results') if src_res.lower() == 'default' else src_res
    output_csv = os.path.join(os.path.dirname(src_folder_old), 'files_matching.csv') if output_csv.lower() == 'default' else output_csv
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        writer.writerow(['key', 'src_pc1', 'src_pc2', 'src_res', 'status'])
        for key, f1, f2 in matched:
            writer.writerow([key, os.path.join(src_folder_old, f1), os.path.join(src_folder_new, f2), os.path.join(src_res, f'{key}_res'), 'matched'])
        for key, f1 in unmatched1:
            writer.writerow([key, os.path.join(src_folder_old, f1), '', '', 'no_pc2'])
        for key, f2 in unmatched2:
            writer.writerow([key, '', os.path.join(src_folder_new, f2), '', 'no_pc1'])

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


def merge_gpkg(list_paths, output_path, crs="EPSG:2056", verbose=False):
    """
    Merge multiple GPKG files into one.
    
    Parameters:
        list_paths: list of paths to GPKG files
        layer_name: name of the layer to read from each GPKG
        output_path: path to the output GPKG file
        crs: coordinate reference system
    """
    # link every layer to the files that have it
    layer_names = {}
    for path in list_paths:
        sub_layer_names = gpd.list_layers(path)["name"].tolist()
        for sublayer in sub_layer_names:
            if sublayer not in layer_names.keys():
                layer_names[sublayer] = [path]
            else:
                layer_names[sublayer].append(path)

    # read files and merge them
    for layer_name, paths_in_layer in layer_names.items():
        gdfs = []
        for path in paths_in_layer:
            try:
                gdf = gpd.read_file(path, layer=layer_name)
                gdfs.append(gdf)
            except Exception as e:
                print(f"Warning: could not read layer '{layer_name}' from {path}: {e}")

        if len(gdfs) == 0:
            print(f"Warning: no data found for layer '{layer_name}'")
            continue

        merged = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=crs)
        merged.to_file(output_path, layer=layer_name, driver="GPKG")
        if verbose:
            print(f"  Layer '{layer_name}': merged {len(gdfs)} files → {len(merged)} features")


def merge_results_from_csv(src_csv, prefix, crs="EPSG:2056", verbose=True):
    df_tiles = pd.read_csv(src_csv, sep=';')
    df_tiles = df_tiles.loc[df_tiles.status == 'matched']

    res = []
    src_res_merged = os.path.join(os.path.dirname(src_csv), 'results_merged')
    os.makedirs(src_res_merged, exist_ok=True)

    for _, row in df_tiles.iterrows():
        src_res = os.path.join(os.path.dirname(src_csv), row.src_res)
        os.makedirs(src_res, exist_ok=True)
        res.append([os.path.join(src_res, x) for x in os.listdir(src_res) if x.endswith('gpkg') and x.split('_')[0] == prefix])

    df_res = pd.DataFrame(res)
    if verbose:
        print(f"Merging {len(df_res)} files:")
    for i in tqdm(range(df_res.values.shape[1]), total=df_res.values.shape[1], desc="Merging"):
    # for _, (_, series) in tqdm(enumerate(df_res.items()), total=len(df_res), desc="Merging"):
        # list_of_files = [f for f in series.to_list() if f]
        list_of_files = df_res.values[:,i].tolist()
        if not list_of_files:
            continue
        merged_file_name = os.path.basename(list_of_files[0]).split('.gpkg')[0] + "_MERGED.gpkg"
        output_path = os.path.join(src_res_merged, merged_file_name)
        merge_gpkg(list_of_files, output_path, crs=crs, verbose=verbose)


def merge_results_from_list(lst_result_paths, src_res_merged, crs="EPSG:2056", verbose=True):
    res = []
    os.makedirs(src_res_merged, exist_ok=True)

    for src_res in lst_result_paths:
        res.append([os.path.join(src_res, x) for x in os.listdir(src_res) if  x.endswith('gpkg')])

    df_res = pd.DataFrame(res)
    if verbose:
        print(f"Merging {len(df_res)} files:")
    for _, (_, series) in tqdm(enumerate(df_res.items()), total=len(df_res.columns), desc="Merging", disable=verbose==False):
        list_of_files = [f for f in series.to_list() if f]
        if not list_of_files:
            continue
        merged_file_name = os.path.basename(list_of_files[0]).split('.gpkg')[0] + "_MERGED.gpkg"
        output_path = os.path.join(src_res_merged, merged_file_name)
        merge_gpkg(list_of_files, output_path, crs=crs, verbose=verbose)


if __name__ == "__main__":
    pass
    # verbose=False
    # conf_prod = OmegaConf.load('./config/production.yaml')
    # conf_one_tile = OmegaConf.load('./config/one_file.yaml')

    # if conf_prod.production.do_merge_results:
    #     merge_results_from_csv(
    #         src_csv=conf_prod.production.src_csv,
    #         prefix=conf_prod.production.prefix,
    #         )