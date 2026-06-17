import os
import shutil
import numpy as np
import open3d as o3d
from time import time
import pickle
from omegaconf import OmegaConf
from postprocessing import postprocessing, remove_A0
from src.icp_utils import \
    read_pc_with_cat_timming, \
    filter_las_by_classification, \
    build_quadtree, run_icp_on_tree, \
    node_to_list, \
    find_node, \
    trim_branch


def ICP_process(conf, verbose=True):
    if verbose:
        print("Starting process (might take several minutes)...")
    time_tot = time()
    # test if files exist
    for id_pc, pc in enumerate([conf.data.src_pc1, conf.data.src_pc2]):
        try:
            assert os.path.exists(pc)
        except:
            raise AttributeError(f"The path given for pc{id_pc} is wrong!") from None

    # === PROCESSING ===
    # prepare results
    os.makedirs(conf.data.src_res, exist_ok=True)
    pointcloud_res = os.path.join(conf.data.src_res, 'pointclouds')
    if conf.args.do_output_transformed:
        os.makedirs(pointcloud_res, exist_ok=True)

    start = time()
    src_result_transforms = os.path.join(conf.data.src_res, f'pyramid_transforms_{conf.data.res_suffixe}.pickle')
    src_result_offset = os.path.join(conf.data.src_res, f'offset.txt')

    tiles = {
        'source': read_pc_with_cat_timming(conf.data.src_pc1, conf.preprocessing.list_cat_to_remove),
        'target': read_pc_with_cat_timming(conf.data.src_pc2, conf.preprocessing.list_cat_to_remove),
    }

    # Center pointclouds
    z_mean = float(np.mean(tiles['source'].z))
    offset = [conf.args.huge_translation[0], conf.args.huge_translation[1], z_mean]

    bbox_dict = {
        "min_bound": (tiles['source'].header.min - offset).tolist(),
        "max_bound": (tiles['source'].header.max - offset).tolist()
    }

    # Process ground
    tiles_ground = {
        'source': filter_las_by_classification(tiles['source'], conf.preprocessing.cat_ground, 'keep'),
        'target': filter_las_by_classification(tiles['target'], conf.preprocessing.cat_ground, 'keep'),
    }

    # Process anthropic
    tiles_anthropic = {
        'source': filter_las_by_classification(tiles['source'], conf.preprocessing.cat_ground, 'remove'),
        'target': filter_las_by_classification(tiles['target'], conf.preprocessing.cat_ground, 'remove'),
    }

    roots = {
        'ground': None,
        'anthropic': None,
    }

    confs = {
        'ground': {
            'min_points': conf.args.min_points_ground,
            'min_tile_size': conf.args.min_tile_size_ground,
            'is_anthropic': False,
        },
        'anthropic': {
            'min_points': conf.args.min_points_anthropic,
            'min_tile_size': conf.args.min_tile_size_anthropic,
            'is_anthropic': True,
        },
    }
    
    time_initializaion = time() - time_tot
    time_quadtree_creation = 0
    time_subclouds_creation = []
    time_icp = []
    time_subclouds_saving = []

    for tiles, mode in zip([tiles_ground, tiles_anthropic], roots.keys()):
        # test if pointcloud empty
        if len(tiles['source'].points) == 0 and len(tiles['target'].points) == 0:
            if verbose:
                print("No points detected for ", mode)
            continue
        
        # apply offset
        for tile in tiles.values():
            tile.translate(np.array([-x for x in offset]))

        # compute normals
        if conf.args.method == 'pointtoplane':
            tiles['target'].estimate_normals(
                o3d.geometry.KDTreeSearchParamHybrid(
                    radius=conf.args.pointtoplane_radius, 
                    max_nn=conf.args.pointtoplane_max_nn,
                    ))

        # numpy arrays
        xyz_src = np.asarray(tiles['source'].points)
        xyz_tgt = np.asarray(tiles['target'].points)

        # build tree
        time0 = time()
        roots[mode] = build_quadtree(
            xyz_src=xyz_src,
            xyz_tgt=xyz_tgt,
            parent=None,
            bbox=bbox_dict,
            indices_src=np.arange(len(xyz_src)),
            indices_tgt=np.arange(len(xyz_tgt)),
            indices_tgt_neigh=np.arange(len(xyz_tgt)),
            level=0,
            min_tile_size=confs[mode]['min_tile_size'],
            min_points=confs[mode]['min_points'],
            is_anthropic=confs[mode]['is_anthropic'],
        )

        time_quadtree_creation += time() - time0

        # run the ICP algorithm on every node of the tree
        run_icp_on_tree(
            node=roots[mode], 
            pc_source=tiles['source'], 
            pc_target=tiles['target'], 
            src_res=pointcloud_res, 
            args=conf.args, 
            time_subclouds_creation=time_subclouds_creation, 
            time_icp=time_icp, 
            time_subclouds_saving=time_subclouds_saving,
            )

    # --- TEMP ---
    src_ground = os.path.join(os.path.dirname(conf.data.src_res), "TEMP_GROUND.pickle")
    src_anthropic = os.path.join(os.path.dirname(conf.data.src_res), "TEMP_ANTHROPIC.pickle")
    with open(src_ground, 'wb') as f:
        pickle.dump(roots['ground'], f)
    with open(src_anthropic, 'wb') as f:
        pickle.dump(roots['anthropic'], f)
    # ---

    # replace nodes in ground by leaves in buildings
    anthropic_nodes = node_to_list(roots['anthropic'])
    anthropic_leaves = [x for x in anthropic_nodes if x.is_leaf == True]
    
    for node in anthropic_leaves:
        if node.level == 0:
            break
        ground_node = find_node(roots['ground'], node.id)
        if ground_node != None:
            parent = ground_node.parent
            trim_branch(ground_node)
            parent.children.append(node)
            node.parent = parent
        else:
            while ground_node == None:
                child = node
                node = node.parent
                ground_node = find_node(roots['ground'], node.id)
            ground_node.children.append(child)
            ground_node.is_leaf = True

    # save final root
    with open(src_result_transforms, 'wb') as f:
        pickle.dump(roots['ground'], f)

    with open(src_result_offset, 'w') as f:
            f.write(f"{offset[0]},{offset[1]},{offset[2]}")

    if verbose:
        print(f"Algorithm executed in {int(time() - start)}s")
        print(f"\n\t Time initialization: {int(time_initializaion)}s")
        print(f"\t Time to create quadtrees: {int(time_quadtree_creation)}s")
        print(f"\t Time to create subclouds: {int(np.sum(time_subclouds_creation))}s")
        if conf.args.do_output_transformed:
            print(f"\t Time to save subclouds: {int(np.sum(time_subclouds_saving))}s")
        print(f"\t Time to ICP: {int(np.sum(time_icp))}s")


    # === POSTPROCESSING ===
    if conf.args.do_postprocessing:
        time_postprocess = time()
        if verbose:
            print("Starting postprocessing...")

        src_out_gpkg = os.path.join(os.path.dirname(src_result_transforms), 'points_translate.gpkg')

        # Postprocess with A0
        if conf.postprocessing.verbose:
            print("\nPostprocessing with initial alignment (w_A0)")
        postprocessing(
            root=roots['ground'], 
            src_out_gpkg=src_out_gpkg, 
            offset=offset, 
            to_keep=conf.postprocessing.to_keep,
            absurd_dist=conf.postprocessing.absurd_dist, 
            suffixe='w_A0', 
            verbose=conf.postprocessing.verbose,
            )

        # Postprocess without A0:
        if conf.postprocessing.verbose:
            print("\nPostprocessing without initial alignment (wo_A0)")
        A0_inv = np.linalg.inv(roots['ground'].global_transform)
        remove_A0(roots['ground'], A0_inv)
        postprocessing(
            root=roots['ground'], 
            src_out_gpkg=src_out_gpkg, 
            offset=offset, 
            to_keep=conf.postprocessing.to_keep,
            absurd_dist=conf.postprocessing.absurd_dist, 
            suffixe='wo_A0', 
            verbose=conf.postprocessing.verbose,
            )
        if conf.args.verbose:
            print(f"Postprocessing executed in {int(time() - time_postprocess)}s")
        print()

    # save config
    shutil.copyfile(
        './config/one_tile.yaml',
        os.path.join(conf.data.src_res, 'config.yaml')
    )

    if verbose:
        # Show duration of process
        delta_time_loop = time() - time_tot
        hours = int(delta_time_loop // 3600)
        min = int((delta_time_loop - 3600 * hours) // 60)
        sec = int(delta_time_loop - 3600 * hours - 60 * min)
        print(f"\n==== COMPLETE PROCESS DONE IN {hours}:{min}:{sec} ====\n")


if __name__ == "__main__":
    conf = OmegaConf.load("./config/one_tile.yaml")
    if conf.data.src_res == "default":
        conf.data.src_res = os.path.join(os.path.dirname(conf.data.src_pc1), 'results')
    o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)
    ICP_process(conf, conf.args.verbose)
    