import os
import pandas as pd
from omegaconf import OmegaConf
from process_one_tile import ICP_process
from tqdm import tqdm
from src.production_utils import preprocess_into_csv, merge_results
import traceback


def production(conf, conf_one_tile, verbose):
    if conf.production.src_csv == 'default':
        conf.production.src_csv = os.path.join(os.path.dirname(conf.production.src_folder_old), 'list_tiles.csv')

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
    conf_one_tile.data.prefix = conf.production.prefix
    for _, row in tqdm(df_tiles.iterrows(), total=len(df_tiles), desc="Processing"):
        try:
            conf_one_tile.data.src_pc1 = row.pc1
            conf_one_tile.data.src_pc2 = row.pc2
            conf_one_tile.data.src_res = row.res
            ICP_process(conf_one_tile, verbose=verbose)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)

    if conf_prod.production.do_merge_results:
            merge_results(
                src_csv=conf_prod.production.src_csv,
                prefix=conf_prod.production.prefix,
                )
            

if __name__ == "__main__":
    verbose=False
    conf_prod = OmegaConf.load('./config/production.yaml')
    conf_one_tile = OmegaConf.load('./config/one_tile.yaml')

    # Prepare csv
    production(conf_prod, conf_one_tile, verbose)

    # if conf_prod.production.do_merge_results:
    #     merge_results(
    #         src_csv=conf_prod.production.src_csv,
    #         prefix=conf_prod.production.prefix,
    #         )
