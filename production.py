import os
import pandas as pd
from omegaconf import OmegaConf
from process_one_tile import ICP_process
from tqdm import tqdm
import csv
import re
from src.production_utils import template_to_regex,  index_folder


def preprocess_into_csv(src_folder_old, src_folder_new, output_csv, pattern_template, verbose=False):
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
    with open(output_csv, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        writer.writerow(['key', 'src_pc1', 'src_pc2', 'src_res', 'status'])
        for key, f1, f2 in matched:
            writer.writerow([key, f1, f2, f'{key}_res', 'matched'])
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


def process_all_in_folder(conf, conf_one_tile, verbose):
    if conf.production.src_csv == 'default':
        conf.production.src_csv = os.path.join(os.path.dirname(conf.production.src_folder_old), 'list_tiles.csv')

    # === PREPROCESSING ===
    if conf.preprocessing.do_preprocessing:
        preprocess_into_csv(
            conf.production.src_folder_old, 
            conf.production.src_folder_new, 
            conf.production.src_csv, 
            conf.preprocessing.pattern, 
            conf.preprocessing.verbose,
            )
    quit()
    df_tiles = pd.read_csv(conf.production.src_csv, sep=';')
    df_tiles = df_tiles.loc[df_tiles.status == 'matched']
    for _, row in tqdm(df_tiles.iterrows(), total=len(df_tiles)):
        conf_one_tile.data.src_pc1 = os.path.join(conf.production.src_folder_old, row.pc1)
        conf_one_tile.data.src_pc2 = os.path.join(conf.production.src_folder_new, row.pc2)
        conf_one_tile.data.src_res = 'default' if row.src_res == 'default' else os.path.join(conf.production.src_folder, row.src_res)
        ICP_process(conf_one_tile, verbose=verbose)


if __name__ == "__main__":
    verbose=False
    conf_prod = OmegaConf.load('./config/production.yaml')
    conf_one_tile = OmegaConf.load('./config/one_tile.yaml')

    # Prepare csv
    process_all_in_folder(conf_prod, conf_one_tile, verbose)
