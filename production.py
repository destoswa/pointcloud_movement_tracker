import os
import pandas as pd
from omegaconf import OmegaConf
from process_one_tile import ICP_process
from tqdm import tqdm


def process_all_in_folder(conf, conf_one_tile, verbose):
    df_tiles = pd.read_csv(conf.production.src_csv, sep=';')
    for _, row in tqdm(df_tiles.iterrows(), total=len(df_tiles)):
        conf_one_tile.data.src_pc1 = os.path.join(conf.production.src_folder, row.pc1)
        conf_one_tile.data.src_pc2 = os.path.join(conf.production.src_folder, row.pc2)
        conf_one_tile.data.src_res = 'default' if row.pc_res == 'default' else os.path.join(conf.production.src_folder, row.pc_res)
        ICP_process(conf_one_tile, verbose=verbose)


if __name__ == "__main__":
    verbose=False
    conf_prod = OmegaConf.load('./config/production.yaml')
    conf_one_tile = OmegaConf.load('./config/one_tile.yaml')
    process_all_in_folder(conf_prod, conf_one_tile, verbose)