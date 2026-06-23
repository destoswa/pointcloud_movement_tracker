import os
import numpy as np
import pickle
from omegaconf import OmegaConf
from time import time
from src.postprocessing_utils import \
    tree_to_list, \
    compute_translation,\
    compute_rotation, \
    detect_absurds, \
    compute_data_for_gpkg, \
    node_to_list, \
    export_points_and_bboxes, \
    remove_A0, find_node


def postprocessing(root, src_out_gpkg, offset, to_keep, absurd_dist_local=5, absurd_dist_global=20, suffixe='', verbose=False):
    # prepare paths
    src_out_gpkg = src_out_gpkg.split('.gpkg')[0] + f"_{suffixe}.gpkg"
    src_out_gpkg_leaves = src_out_gpkg.split('.gpkg')[0] + f"_leaves.gpkg"
    src_out_gpkg_layers_tiles = src_out_gpkg.split('.gpkg')[0] + f"_layers_tiles.gpkg"
    src_out_gpkg_layers_centers = src_out_gpkg.split('.gpkg')[0] + f"_layers_centers.gpkg"

    # store nodes in a list
    list_nodes, list_nodes_per_level = [], []
    tree_to_list(root, list_nodes, list_nodes_per_level)

    # Compute metrics:
    time0 = time()
    compute_translation(root)
    compute_rotation(root)
    
    if verbose:
        print("Time to compute translation and rotation: ", time() - time0)

    # Detect absurd values
    original_len = len(root)
    time0 = time()
    counter = detect_absurds(root, absurd_dist_local, absurd_dist_global)
    
    if verbose:
        print("Time to detect absurds: ", time() - time0)

    if verbose:
        print(f"Number of absurd values: {counter} ({np.round(counter/original_len*100, 2)}%)")

    # Gather data for GPKG
    time0 = time()
    data, bbox_data = compute_data_for_gpkg(root, offset)
    if verbose:
        print("Time to compute data for gpkg: ", time() - time0)

    columns = node_to_list(root)[0]

    # Export all tiles
    time0 = time()
    if to_keep.full_tree:
        export_points_and_bboxes(
            data=data,
            bbox_data=bbox_data,
            columns=columns,
            output_path=src_out_gpkg,
            offset=offset,
            do_clip_overlaps=False,
            verbose=verbose,
        )

    # Export only leaves
    data_leaves = [x for x in data if x[-2] == True]
    mask_leaves = np.array([x[-2] for x in data], dtype=np.bool)
    bbox_data_leaves = list(np.array(bbox_data)[mask_leaves])

    export_points_and_bboxes(
        data=data_leaves,
        bbox_data=bbox_data_leaves,
        columns=columns,
        output_path=src_out_gpkg_leaves,
        offset=offset,
        do_clip_overlaps=True,
        verbose=verbose,
    )

    # Layer by layer
    if to_keep.layers:
        if verbose:
            print("Num of tiles per level:")
        for lvl in range(len(list_nodes_per_level)):
            if verbose:
                print("\tlevel: ", lvl, ' - num subtiles: ', len(list_nodes_per_level[lvl]))

            data, bbox_data = compute_data_for_gpkg(list_nodes_per_level[lvl], offset)

            export_points_and_bboxes(
                data=data,
                bbox_data=bbox_data,
                columns=columns,
                output_path=src_out_gpkg_layers_tiles,
                to_export='boxes',
                offset=offset,
                layer_name=f"Level {lvl}",
                verbose=verbose,
            )

            export_points_and_bboxes(
                data=data,
                bbox_data=bbox_data,
                columns=columns,
                output_path=src_out_gpkg_layers_centers,
                to_export='points',
                offset=offset,
                layer_name=f"Level {lvl}",
                verbose=verbose,
            )
    
    if verbose:
        print("Time to export different version: ", time() - time0)

if __name__ == "__main__":
    conf = OmegaConf.load('./config/one_tile.yaml')
    if conf.postprocessing.src_transforms == 'default':
        if conf.data.src_res == 'default':
            conf.data.src_res = os.path.join(os.path.dirname(conf.data.src_pc1), 'results')
        src_transforms = os.path.join(conf.data.src_res, f'pyramid_transforms_{conf.data.res_suffixe}.pickle')
    else:
        src_transforms = conf.postprocessing.src_transforms

    # prepare paths
    src_out_gpkg = os.path.join(os.path.dirname(src_transforms), 'points_translate.gpkg')
    src_offset = os.path.join(os.path.dirname(src_transforms), 'offset.txt')

    with open(src_transforms, 'rb') as f:
        root = pickle.load(f)
    offset = np.loadtxt(src_offset, delimiter=',')

    # Postprocess with A0
    if conf.postprocessing.to_keep.initial_alignment in ['with', 'both']:
        print("Postprocessing with initial alignment (w_A0)")
        postprocessing(
            root=root, 
            src_out_gpkg=src_out_gpkg, 
            offset=offset, 
            to_keep=conf.postprocessing.to_keep,
            absurd_dist_local=conf.postprocessing.absurd_dist_local,
            absurd_dist_global=conf.postprocessing.absurd_dist_global, 
            suffixe='w_A0', 
            verbose=conf.postprocessing.verbose,
            )

    # Postprocess without A0:
    if conf.postprocessing.to_keep.initial_alignment in ['without', 'both']:
        print("\nPostprocessing without initial alignment (wo_A0)")
        A0_inv = np.linalg.inv(root.global_transform)
        remove_A0(root, A0_inv)
        postprocessing(
            root=root, 
            src_out_gpkg=src_out_gpkg, 
            offset=offset, 
            to_keep=conf.postprocessing.to_keep,
            absurd_dist_local=conf.postprocessing.absurd_dist_local,
            absurd_dist_global=conf.postprocessing.absurd_dist_global, 
            suffixe='wo_A0', 
            verbose=conf.postprocessing.verbose,
            )

    print()










# === EXAMPLE CODE WHEN USING COHERENCE ===

# from src.coherence import compute_spatial_coherence, compute_magnitude_zscore, compute_rotation_angles, compute_confidence

    # # Compute coherence indexes
    # translation_x = [node.metrics['translation_x'] for node in list_nodes]
    # translation_y = [node.metrics['translation_y'] for node in list_nodes]
    # displacement = [node.metrics['Disp3D'] for node in list_nodes]
    # planarity = [float(node.planarity) for node in list_nodes]
    # rotation_angles = [node.metrics['rotation_angle'] for node in list_nodes]

    # spatial_coherences = compute_spatial_coherence(list_nodes, translation_x, translation_y, 40)
    # magnitude_zscores = compute_magnitude_zscore(list_nodes, displacement, 40)

    # mask_artifact = (
    #     (np.array(spatial_coherences) < 0.707) |       # direction disagrees with neighbors (> 45°)
    #     (np.array(magnitude_zscores) > 2.5) |           # magnitude is outlier among neighbors
    #     (np.array(rotation_angles) > 5) |              # large rotation
    #     (np.array(planarity) > 0.999)           # flat surface → degenerate ICP
    # )
    # print(f"Number of masked samples: {np.sum(mask_artifact)} ({np.round(np.sum(mask_artifact)/mask_artifact.shape[0]*100, 2)}%)")

    # for node, coherence, magnitude, rotation, artifact in zip(list_nodes, spatial_coherences, magnitude_zscores, rotation_angles, mask_artifact):
    #     node.metrics['spatial_coherence'] = coherence
    #     node.metrics['magnitude_zscore'] = magnitude
    #     node.metrics['rotation_angle'] = rotation
    #     node.metrics['confidence'] = compute_confidence(coherence, magnitude, rotation, node.planarity, node.fitness, node.inlier_rmse, 
    #                                                     w_fitness=0, w_rmse=0)
    #     node.metrics['is_artifact'] = bool(artifact)

# ================
