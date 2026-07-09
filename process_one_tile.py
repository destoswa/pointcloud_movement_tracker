import os
import shutil
import numpy as np
import open3d as o3d
from time import time
import pickle
from omegaconf import OmegaConf
from tqdm import tqdm
from postprocessing import postprocessing, remove_A0
from src.icp_utils import \
    read_pc_with_cat_timming, \
    filter_las_by_classification, \
    build_quadtree, run_icp_on_tree, \
    node_to_list, \
    find_node, \
    trim_branch, \
    get_nodes_of_level
from src.format_conversions import convert_one_file


def ICP_process(conf, verbose=True):
    if conf.data.src_res == "default":
        conf.data.src_res = os.path.join(os.path.dirname(conf.data.src_pc1), 'results')
    o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)
    
    if verbose:
        print("Starting process (might take several minutes)...")
    time_tot = time()

    # test if files exist
    for id_pc, pc in enumerate([conf.data.src_pc1, conf.data.src_pc2]):
        try:
            assert os.path.exists(pc)
        except:
            raise AttributeError(f"The path given for pc{id_pc} is wrong!") from None
        
    # === PREPROCESSING ===
    pointcloud_formats = [os.path.splitext(x)[1][1:] for x in [conf.data.src_pc1, conf.data.src_pc2]]
    files_to_remove = []
    if not all([x.lower() in ['las', 'laz'] for x in pointcloud_formats]):
        for pc_key, format in zip(['data.src_pc1', 'data.src_pc2'], pointcloud_formats):
            if format not in ['las', 'laz']:
                src_file_original = OmegaConf.select(conf, pc_key)
                if verbose:
                    print(f"Converting following file into LAZ: {src_file_original}")
                src_file_out = os.path.splitext(src_file_original)[0] + '.laz'

                convert_one_file(
                    src_file_in=src_file_original,
                    src_file_out=src_file_out,
                    in_type=format,
                    out_type='laz'
                )

                OmegaConf.update(conf, pc_key, src_file_out)

                files_to_remove.append(src_file_out)

    # === PROCESSING ===
    # prepare results
    os.makedirs(conf.data.src_res, exist_ok=True)
    pointcloud_res = os.path.join(conf.data.src_res, 'pointclouds')
    if conf.args.do_output_transformed:
        os.makedirs(pointcloud_res, exist_ok=True)

    start = time()
    src_result_transforms = os.path.join(conf.data.src_res, f'pyramid_transforms_{conf.data.res_suffixe}.pickle')
    src_result_offset = os.path.join(conf.data.src_res, f'offset.txt')
    time0 = time()
    tiles_original = {
        'source': read_pc_with_cat_timming(conf.data.src_pc1, conf.args.field_names[3], conf.categories.list_cat_to_remove),
        'target': read_pc_with_cat_timming(conf.data.src_pc2, conf.args.field_names[3], conf.categories.list_cat_to_remove),
    }
    if verbose:
        print("time to load: ", time() - time0)
    
    # Remove translated files
    for file_src in files_to_remove:
        os.remove(file_src)

    # Center pointclouds
    z_mean = float(np.mean(tiles_original['source'].z))
    offset = [conf.args.huge_translation[0], conf.args.huge_translation[1], z_mean]

    bbox_dict = {
        "min_bound": (tiles_original['source'].header.min - offset).tolist(),
        "max_bound": (tiles_original['source'].header.max - offset).tolist()
    }

    time0 = time()

    # Process categories
    if conf.categories.split_ground_anthropic:
        # Process ground
        tiles_ground = {
            'source': filter_las_by_classification(tiles_original['source'], conf.categories.cat_ground, conf.args.field_names, 'keep'),
            'target': filter_las_by_classification(tiles_original['target'], conf.categories.cat_ground, conf.args.field_names, 'keep'),
        }

        # Process anthropic
        tiles_anthropic = {
            'source': filter_las_by_classification(tiles_original['source'], conf.categories.cat_ground, conf.args.field_names, 'remove'),
            'target': filter_las_by_classification(tiles_original['target'], conf.categories.cat_ground, conf.args.field_names, 'remove'),
        }

        roots = {
            'ground': None,
            'anthropic': None,
        }

        tiles_to_process = [tiles_ground, tiles_anthropic]
    else:
        pc_source = o3d.geometry.PointCloud()
        pc_source.points = o3d.utility.Vector3dVector(
            np.stack([getattr(tiles_original['source'], conf.args.field_names[0]) * tiles_original['source'].header.scale[0] + tiles_original['source'].header.offset[0],
                    getattr(tiles_original['source'], conf.args.field_names[1]) * tiles_original['source'].header.scale[1] + tiles_original['source'].header.offset[1],
                    getattr(tiles_original['source'], conf.args.field_names[2]) * tiles_original['source'].header.scale[2] + tiles_original['source'].header.offset[2]], axis=1)
        )
        pc_target = o3d.geometry.PointCloud()
        pc_target.points = o3d.utility.Vector3dVector(
            np.stack([getattr(tiles_original['target'], conf.args.field_names[0]) * tiles_original['target'].header.scale[0] + tiles_original['target'].header.offset[0],
                    getattr(tiles_original['target'], conf.args.field_names[1]) * tiles_original['target'].header.scale[1] + tiles_original['target'].header.offset[1],
                    getattr(tiles_original['target'], conf.args.field_names[2]) * tiles_original['target'].header.scale[2] + tiles_original['target'].header.offset[2]], axis=1)
        )
        tiles_ground = {
            'source': pc_source,
            'target': pc_target,
        }

        tiles_to_process = [tiles_ground]

        roots = {
            'ground': None,
        }

    if verbose:
        print("time to filter: ", time() - time0)

    confs = {
        'ground': {
            'min_points': conf.categories.min_points_ground,
            'min_tile_size': conf.categories.min_tile_size_ground,
            'is_anthropic': False,
        },
        'anthropic': {
            'min_points': conf.categories.min_points_anthropic,
            'min_tile_size': conf.categories.min_tile_size_anthropic,
            'is_anthropic': True,
        },
    }
    
    time_initializaion = time() - time_tot
    time_quadtree_creation = 0
    time_subclouds_creation = []
    time_icp = []
    time_subclouds_saving = []

    # # --- TEMP ---
    # src_ground = os.path.join(os.path.dirname(conf.data.src_res), "TEMP_GROUND.pickle")
    # src_anthropic = os.path.join(os.path.dirname(conf.data.src_res), "TEMP_ANTHROPIC.pickle")
    # with open(src_ground, 'rb') as f:
    #     roots['ground'] = pickle.load(f)
    # with open(src_anthropic, 'rb') as f:
    #     roots['anthropic'] = pickle.load(f)
    # # ---

    for tiles, mode in zip(tiles_to_process, roots.keys()):
        # test if pointcloud empty
        if len(tiles['source'].points) == 0 and len(tiles['target'].points) == 0:
            if verbose:
                print("No points detected for ", mode)
            continue
        
        # apply offset
        for tile in tiles.values():
            tile.translate(np.array([-x for x in offset]))

        # extract points in arrays
        xyz_src = np.asarray(tiles['source'].points, dtype=np.float32)
        xyz_tgt = np.asarray(tiles['target'].points, dtype=np.float32)

        area = ((bbox_dict['max_bound'][0] - bbox_dict['min_bound'][0]) * (bbox_dict['max_bound'][1] - bbox_dict['min_bound'][1])) / 1e6
        lvl_to_process = max([0, int(np.ceil(np.log(area/conf.args.max_area)/np.log(4)))])

        # generate indices if root small enough
        if area <= conf.args.max_area:
            indices_src=np.arange(len(xyz_src), dtype=np.int32)
            indices_tgt=np.arange(len(xyz_tgt), dtype=np.int32)
            indices_tgt_neigh=np.arange(len(xyz_tgt), dtype=np.int32)
        else:
            indices_src, indices_tgt, indices_tgt_neigh = None, None, None

        # build tree
        time0 = time()
        roots[mode] = build_quadtree(
            xyz_src=xyz_src,
            xyz_tgt=xyz_tgt,
            parent=None,
            bbox=bbox_dict,
            indices_src=indices_src,
            indices_tgt=indices_tgt,
            indices_tgt_neigh=indices_tgt_neigh,
            level=0,
            min_tile_size=confs[mode]['min_tile_size'],
            min_points=confs[mode]['min_points'],
            max_area=conf.args.max_area,
            is_anthropic=confs[mode]['is_anthropic'],
        )
        if verbose:
            print("time to build quadtree: ", time() - time0)
        time_quadtree_creation += time() - time0

        # # === TEMP ===
        # src_ground = os.path.join(os.path.dirname(conf.data.src_res), "TEMP_GROUND.pickle")
        # with open(src_ground, 'wb')   as f:
        #     pickle.dump(roots['ground'], f)
        # # ===============================

        # arguments for normal computation
        do_compute_normals = conf.args.method == 'pointtoplane' or (conf.args.method == 'mix' and mode == 'ground')
        args_normal = {
            "do_compute_normals": do_compute_normals,
            "radius": conf.args.pointtoplane_radius,
            "max_nn": conf.args.pointtoplane_max_nn,
            }
        
        # run the ICP algorithm on every node of the tree
        lst_tiles_to_icp = get_nodes_of_level(roots[mode], lvl_to_process)
        if verbose:
            print(f"Processing ICP on {len(lst_tiles_to_icp)} tile{'s' if len(lst_tiles_to_icp) > 1 else ''} of level {lvl_to_process} and area {np.round(area / 4**lvl_to_process, 2)}km^2:")
        for _, node in tqdm(enumerate(lst_tiles_to_icp), total=len(lst_tiles_to_icp), desc="Processing", disable=verbose==False):
            run_icp_on_tree(
                pc_source=tiles['source'], 
                pc_target=tiles['target'], 
                node=node, 
                src_res=pointcloud_res, 
                args=conf.args, 
                time_subclouds_creation=time_subclouds_creation, 
                time_icp=time_icp, 
                time_subclouds_saving=time_subclouds_saving,
                pointtoplane_args=args_normal,
                mode=mode,
                )

    # # --- TEMP ---
    # src_ground = os.path.join(os.path.dirname(conf.data.src_res), "TEMP_GROUND.pickle")
    # src_anthropic = os.path.join(os.path.dirname(conf.data.src_res), "TEMP_ANTHROPIC.pickle")
    # with open(src_ground, 'wb')   as f:
    #     pickle.dump(roots['ground'], f)
    # with open(src_anthropic, 'wb') as f:
    #     pickle.dump(roots['anthropic'], f)
    # # ---

    # replace nodes in ground by leaves in buildings
    if conf.categories.split_ground_anthropic:
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
                child.parent = ground_node
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
            absurd_dist_local=conf.postprocessing.absurd_dist_local,
            absurd_dist_global=conf.postprocessing.absurd_dist_global, 
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
            absurd_dist_local=conf.postprocessing.absurd_dist_local,
            absurd_dist_global=conf.postprocessing.absurd_dist_global, 
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
    ICP_process(conf, conf.args.verbose)
    