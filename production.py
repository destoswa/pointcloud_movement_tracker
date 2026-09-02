import os
import pickle
import numpy as np
import pandas as pd
from omegaconf import OmegaConf
from time import time
from process_one_file import ICP_process
from tqdm import tqdm
from tkinter import messagebox as mb
from src.production_utils import preprocess_into_csv, merge_results_from_csv
import traceback
from omegaconf import OmegaConf
from postprocessing import postprocessing
from src.postprocessing_utils import remove_A0


def apply_postprocessing(conf, verbose):
    if verbose:
        print("Starting postprocessing...")
    src_result_transforms = os.path.join(conf.data.src_res, 'quadtree_transforms.pickle')
    src_out_gpkg = os.path.join(os.path.dirname(src_result_transforms), 'quadtree.gpkg')
    src_offset = os.path.join(os.path.dirname(src_result_transforms), 'offset.txt')
    keep_full_tree = conf.postprocessing.to_keep.full_tree
    keep_layers = conf.postprocessing.to_keep.layers

    with open(src_result_transforms, 'rb') as f:
        root = pickle.load(f)
    offset = np.loadtxt(src_offset, delimiter=',')
    # Postprocess with A0
    if verbose:
        print("\nPostprocessing with initial alignment (w_A0)")

    postprocessing(
        root=root, 
        src_out_gpkg=src_out_gpkg, 
        offset=offset, 
        keep_full_tree=keep_full_tree,
        keep_layers=keep_layers,
        absurd_dist_local=conf.postprocessing.absurd_dist_local,
        absurd_dist_global=conf.postprocessing.absurd_dist_global, 
        prefix=conf.production.prefix, 
        suffix='w_A0', 
        crs=conf.data.crs,
        verbose=conf.postprocessing.verbose,
        )

    # Postprocess without A0:
    if verbose:
        print("\nPostprocessing without initial alignment (wo_A0)")
        
    A0_inv = np.linalg.inv(root.global_transform)
    remove_A0(root, A0_inv)

    postprocessing(
        root=root, 
        src_out_gpkg=src_out_gpkg, 
        offset=offset, 
        keep_full_tree=keep_full_tree,
        keep_layers=keep_layers,
        absurd_dist_local=conf.postprocessing.absurd_dist_local,
        absurd_dist_global=conf.postprocessing.absurd_dist_global, 
        prefix=conf.production.prefix, 
        suffix='wo_A0', 
        crs=conf.data.crs,
        verbose=conf.postprocessing.verbose,
        )


def production(conf):
    time_start = time()
    
    if conf.production.src_csv == 'default':
        conf.production.src_csv = os.path.join(os.path.dirname(conf.preprocessing.src_folder_old), 'list_tiles.csv')

    # === PREPROCESSING ===
    if conf.preprocessing.do_preprocessing:
        preprocess_into_csv(
            conf.preprocessing.src_folder_old, 
            conf.preprocessing.src_folder_new, 
            conf.preprocessing.src_res,
            conf.production.src_csv, 
            conf.preprocessing.pattern, 
            conf.preprocessing.verbose,
            )

    df_tiles = pd.read_csv(conf.production.src_csv, sep=';')
    df_tiles = df_tiles.loc[df_tiles.status == 'matched']

    print("\nProducing on valid pairs of files:")
    conf.data.prefix = conf.production.prefix

    # Test if the resulting folder already contains something and prepare list of files accordingly
    if len(os.listdir(os.path.dirname(df_tiles.src_res[0]))) > 0:
        res=mb.askquestion('Not empty folder', 'The resulting folder seems to already contain folders. Do you want to resume from there? (if no, will start from scratch)')
        if res == 'yes' :
            conf.production.do_skip_existing = True
        else :
            conf.production.do_skip_existing = False

    if conf.production.do_skip_existing:
        list_rows = [row for _, row in df_tiles.iterrows() if not os.path.exists(os.path.join(row.src_res, 'config.yaml'))]
    else:
        list_rows = [row for _, row in df_tiles.iterrows()]

    # Loop over the different files
    for _, row in tqdm(enumerate(list_rows), total=len(list_rows), desc="Processing"):
        try:
            conf.data.src_pc1 = os.path.join(os.path.dirname(conf.production.src_csv), row.src_pc1)
            conf.data.src_pc2 = os.path.join(os.path.dirname(conf.production.src_csv), row.src_pc2)
            conf.data.src_res = os.path.join(os.path.dirname(conf.production.src_csv), row.src_res)

            # If only applying postprocessing on existing results or doing the full process
            if conf.production.postprocess_only:
                apply_postprocessing(conf, verbose=conf.production.verbose)
            else:
                ICP_process(conf, verbose=conf.production.verbose)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)

    # Merge results
    if conf.production.do_merge_results:
        merge_results_from_csv(
            src_csv=conf.production.src_csv,
            prefix=conf.production.prefix,
            verbose=conf.production.verbose
            )

    # Save results
    src_conf = os.path.join(os.path.dirname(conf.production.src_csv), 'config.yaml')
    OmegaConf.save(conf, src_conf)

    # Show duration of process
    delta_time_loop = time() - time_start
    hours = int(delta_time_loop // 3600)
    min = int((delta_time_loop - 3600 * hours) // 60)
    sec = int(delta_time_loop - 3600 * hours - 60 * min)
    print(f"\n==== COMPLETE PROCESS DONE IN {hours}:{min}:{sec} ====\n")


if __name__ == "__main__":
    conf_prod = OmegaConf.load('./config/production.yaml')
    conf_one_tile = OmegaConf.load('./config/one_file.yaml')
    conf = OmegaConf.merge(conf_prod, conf_one_tile)

    production(conf)
