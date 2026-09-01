import os
import shutil
import numpy as np
import open3d as o3d
from itertools import product
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
    prepare_files, \
    get_nodes_of_level
from src.format_conversions import convert_one_file
from src.production_utils import merge_results_from_list


def ICP_process(conf, bbox_offset=None, verbose=True):
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
            raise AttributeError(f"The path given for pc{id_pc+1} is wrong!") from None
        
    # === PREPROCESSING ===
    pointcloud_formats = [os.path.splitext(x)[1][1:] for x in [conf.data.src_pc1, conf.data.src_pc2]]
    files_to_remove = []
    if not all([x.lower() in ['las', 'laz'] for x in pointcloud_formats]):
        src_pc1, src_pc2, files_to_remove = prepare_files(conf.data.src_pc1, conf.data.src_pc2, verbose)
        OmegaConf.update(conf, 'data.src_pc1', src_pc1)
        OmegaConf.update(conf, 'data.src_pc2', src_pc2)

    # === PROCESSING ===
    # prepare results
    os.makedirs(conf.data.src_res, exist_ok=True)
    pointcloud_res = os.path.join(conf.data.src_res, 'pointclouds')
    if conf.args.do_output_transformed:
        os.makedirs(pointcloud_res, exist_ok=True)

    start = time()
    src_result_transforms = os.path.join(conf.data.src_res, 'quadtree_transforms.pickle')
    src_result_offset = os.path.join(conf.data.src_res, f'offset.txt')
    time0 = time()

    # load pointclouds
    list_anthropic = [conf.categories.cat_anthropic] if isinstance(conf.categories.cat_anthropic, int) else conf.categories.cat_anthropic
    list_ground = [conf.categories.cat_ground] if isinstance(conf.categories.cat_ground, int) else conf.categories.cat_ground
    list_cat_to_keep = [x for row in [list_anthropic, list_ground] for x in row]
    tiles_original = {
        'source': read_pc_with_cat_timming(conf.data.src_pc1, conf.args.field_names[3], list_cat_to_keep, conf.categories.no_cat),
        'target': read_pc_with_cat_timming(conf.data.src_pc2, conf.args.field_names[3], list_cat_to_keep, conf.categories.no_cat),
    }
    if verbose:
        print("time to load: ", time() - time0)
    
    # Remove translated files
    for file_src in files_to_remove:
        os.remove(file_src)


    if bbox_offset == None:
        # Center pointclouds
        x_mean = float(np.mean(tiles_original['source'].x))
        y_mean = float(np.mean(tiles_original['source'].y))
        z_mean = float(np.mean(tiles_original['source'].z))

        # TEMP TEST OFFEST IMPACT
        def random_point_on_circle(xy, radius=100):
            angle = np.random.uniform(0, 2 * np.pi)
            xy_prime = (
                xy[0] + radius * np.cos(angle),
                xy[1] + radius * np.sin(angle)
            )
            return xy_prime

        xy = np.array([x_mean, y_mean])
        [x_prime, y_prime] = random_point_on_circle(xy, 0)
        # =========

        offset = np.array([x_prime, y_prime, z_mean])

        bbox_dict = {
            "min_bound": (tiles_original['source'].header.min - offset).tolist(),
            "max_bound": (tiles_original['source'].header.max - offset).tolist()
        }
    else:
        bbox_dict = bbox_offset[0]
        offset = bbox_offset[1]
        bbox_dict['min_bound'] = [x - y for x,y in zip(bbox_dict['min_bound'], offset)]
        bbox_dict['max_bound'] = [x - y for x,y in zip(bbox_dict['max_bound'], offset)]

    time0 = time()

    # set split to False if no_cat
    conf.categories.split_ground_anthropic = bool(conf.categories.split_ground_anthropic * (conf.categories.no_cat==False))

    # Process categories
    if conf.categories.split_ground_anthropic:
        # Process ground
        tiles_ground = {
            'source': filter_las_by_classification(tiles_original['source'], conf.categories.cat_ground, conf.args.field_names),
            'target': filter_las_by_classification(tiles_original['target'], conf.categories.cat_ground, conf.args.field_names),
        }

        # Process anthropic
        tiles_anthropic = {
            'source': filter_las_by_classification(tiles_original['source'], conf.categories.cat_anthropic, conf.args.field_names),
            'target': filter_las_by_classification(tiles_original['target'], conf.categories.cat_anthropic, conf.args.field_names),
        }

        # do not postprocess if not enough points
        if max([len(tiles_ground['source'].points), len(tiles_ground['target'].points)]) < conf.categories.min_points_ground or \
        max([len(tiles_anthropic['source'].points), len(tiles_anthropic['target'].points)]) < conf.categories.min_points_anthropic:
            return -1
    
        roots = {
            'ground': None,
            'anthropic': None,
        }

        tiles_to_process = [tiles_ground, tiles_anthropic]
    else:
        pc_source = o3d.geometry.PointCloud()

        # define if no removal of points at all or removal of the ones that are not in ground and anthropic (e.g. vegetation)
        # if conf.categories.no_cat:
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

        # do not postprocess if not enough points
        if max([len(tiles_ground['source'].points), len(tiles_ground['target'].points)]) < conf.categories.min_points_ground:
            return -1
        
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

        # generate indices if root small enough
        indices_src=np.arange(len(xyz_src), dtype=np.int32)
        indices_tgt=np.arange(len(xyz_tgt), dtype=np.int32)
        indices_tgt_neigh=np.arange(len(xyz_tgt), dtype=np.int32)

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
            grid_pos=[0,0],
            is_anthropic=confs[mode]['is_anthropic'],
        )
        if verbose:
            print("time to build quadtree: ", time() - time0)
        time_quadtree_creation += time() - time0

        # arguments for normal computation
        do_compute_normals = conf.args.method == 'pointtoplane' or (conf.args.method == 'mix' and mode == 'ground')
        args_normal = {
            "do_compute_normals": do_compute_normals,
            "radius": conf.args.pointtoplane_radius,
            "max_nn": conf.args.pointtoplane_max_nn,
            }
        
        # run the ICP algorithm on every node of the tree
        if verbose:
            print("Processing ICP on every node of the tree (might take a few minutes):")
        run_icp_on_tree(
            pc_source=tiles['source'], 
            pc_target=tiles['target'], 
            node=roots[mode], 
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

    # do not postprocess if not quadtree
    if len(roots['ground']) == 0:
        return -1

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

        src_out_gpkg = os.path.join(os.path.dirname(src_result_transforms), 'quadtree.gpkg')
        keep_full_tree = conf.postprocessing.to_keep.full_tree
        keep_layers = conf.postprocessing.to_keep.layers

        # Postprocess with A0
        if verbose:
            print("\nPostprocessing with initial alignment (w_A0)")

        postprocessing(
            root=roots['ground'], 
            src_out_gpkg=src_out_gpkg, 
            offset=offset, 
            keep_full_tree=keep_full_tree,
            keep_layers=keep_layers,
            absurd_dist_local=conf.postprocessing.absurd_dist_local,
            absurd_dist_global=conf.postprocessing.absurd_dist_global, 
            prefix=conf.data.res_prefix, 
            suffix='w_A0', 
            crs=conf.data.crs,
            verbose=conf.postprocessing.verbose,
            )

        # Postprocess without A0:
        if verbose:
            print("\nPostprocessing without initial alignment (wo_A0)")
            
        A0_inv = np.linalg.inv(roots['ground'].global_transform)
        remove_A0(roots['ground'], A0_inv)

        postprocessing(
            root=roots['ground'], 
            src_out_gpkg=src_out_gpkg, 
            offset=offset, 
            keep_full_tree=keep_full_tree,
            keep_layers=keep_layers,
            absurd_dist_local=conf.postprocessing.absurd_dist_local,
            absurd_dist_global=conf.postprocessing.absurd_dist_global, 
            prefix=conf.data.res_prefix, 
            suffix='wo_A0', 
            crs=conf.data.crs,
            verbose=conf.postprocessing.verbose,
            )
        if conf.args.verbose:
            print(f"Postprocessing executed in {int(time() - time_postprocess)}s")

    # save config
    shutil.copyfile(
        './config/one_file.yaml',
        os.path.join(conf.data.src_res, 'config.yaml')
    )

    if verbose:
        # Show duration of process
        delta_time_loop = time() - time_tot
        hours = int(delta_time_loop // 3600)
        min = int((delta_time_loop - 3600 * hours) // 60)
        sec = int(delta_time_loop - 3600 * hours - 60 * min)
        print(f"\n==== COMPLETE PROCESS DONE IN {hours}:{min}:{sec} ====\n")

    return 0


def one_file(conf, verbose):
    if conf.data.do_tiling:
        if conf.args.verbose:
            print("Tiling at kilometric scale")

        # load files
        if conf.data.src_res == "default":
            src_final_res = os.path.join(os.path.dirname(conf.data.src_pc1), 'results')
        else:
            src_final_res = conf.data.src_res
        o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)

        # test if files exist
        for id_pc, pc in enumerate([conf.data.src_pc1, conf.data.src_pc2]):
            try:
                assert os.path.exists(pc)
            except:
                raise AttributeError(f"The path given for pc{id_pc+1} is wrong!") from None
            
        # === PREPROCESSING ===
        pointcloud_formats = [os.path.splitext(x)[1][1:] for x in [conf.data.src_pc1, conf.data.src_pc2]]
        files_to_remove = []
        if not all([x.lower() in ['las', 'laz'] for x in pointcloud_formats]):
            src_pc1, src_pc2, files_to_remove = prepare_files(conf.data.src_pc1, conf.data.src_pc2, verbose)
            OmegaConf.update(conf, 'data.src_pc1', src_pc1)
            OmegaConf.update(conf, 'data.src_pc2', src_pc2)
            
        big_tiles = {
                'source': read_pc_with_cat_timming(conf.data.src_pc1, "", [], True),
                'target': read_pc_with_cat_timming(conf.data.src_pc2, "", [], True),
            }
        
        # find intersect of bboxes
        bboxes = {
            item: {
                "min_bound": (x.header.min).tolist(),
                "max_bound": (x.header.max).tolist(),
                } for item, x in big_tiles.items()
                }
        bbox_intersect = {
            "min_bound": [max(y[i] for y in [x['min_bound'] for x in bboxes.values()]) for i in range(3)],
            "max_bound": [min(y[i] for y in [x['max_bound'] for x in bboxes.values()]) for i in range(3)],
        }

        bbox_rounded = {
            "min_bound": [int(x // 1000 * 1000) if id_x < 2 else x for id_x, x in enumerate(bbox_intersect['min_bound'])],
            "max_bound": [int((x // 1000 + 1) * 1000) if id_x < 2 else x for id_x, x in enumerate(bbox_intersect['max_bound'])],
        }

        # (create grid)

        # create all sublaz files in temp folder
        src_temp_folder = os.path.join(os.path.dirname(src_final_res), "temp_subtiles")
        src_temp_res = os.path.join(src_temp_folder, 'results')
        os.makedirs(src_temp_folder, exist_ok=True)
        os.makedirs(src_temp_res, exist_ok=True)

        range_x = (bbox_rounded['max_bound'][0] - bbox_rounded['min_bound'][0]) // 1000
        range_y = (bbox_rounded['max_bound'][1] - bbox_rounded['min_bound'][1]) // 1000

        list_ranges = list(product(range(range_x), range(range_y)))

        if conf.args.verbose:
            print("Creating tiles:")
        lst_tiles_to_process = {}
        lst_tiles_to_process_path = {}
        lst_tiles_to_process_res = {}
        lst_bboxes = {}
        for _, (x,y) in tqdm(enumerate(list_ranges), total=len(list_ranges)):
            xmin, xmax = bbox_rounded['min_bound'][0] + x * 1000, bbox_rounded['min_bound'][0] + (x + 1) * 1000
            ymin, ymax = bbox_rounded['min_bound'][1] + y * 1000, bbox_rounded['min_bound'][1] + (y + 1) * 1000
            name = f"{x}_{y}"
            lst_bboxes[name] = {
                'min_bound': [xmin, ymin, bbox_rounded['min_bound'][2]],
                'max_bound': [xmax, ymax, bbox_rounded['max_bound'][2]],
            }
            tiles = {}
            for mode, las in big_tiles.items():
                mask = (
                    (las.x >= xmin) & (las.x <= xmax) &
                    (las.y >= ymin) & (las.y <= ymax)
                )

                tiles[mode] = las[mask]

            skip = False
            for tile in tiles.values():
                if len(tile.points) == 0:
                    skip = True
                    break
            if skip:
                continue

            lst_tiles_to_process_path[name] = []
            lst_tiles_to_process_res[name] = os.path.join(src_temp_res, f"res_{name}")
            for mode, tile in tiles.items():
                src_tile = os.path.join(src_temp_folder, f"tile_{name}_{mode}.laz")
                lst_tiles_to_process_path[name].append(src_tile)
                tile.write(src_tile)

            lst_tiles_to_process[name] = [tile for tile in tiles.values()]

        # run ICP_process on all files
        if conf.args.verbose:
            print("Computing ICP on all tiles")
        lst_to_remove = []
        for _, (name, tile) in tqdm(enumerate(lst_tiles_to_process.items()), total=len(lst_tiles_to_process)):
            conf.data.src_pc1 = lst_tiles_to_process_path[name][0]
            conf.data.src_pc2 = lst_tiles_to_process_path[name][1]
            conf.data.src_res = lst_tiles_to_process_res[name]
            bbox_offset = [
                lst_bboxes[name],
                [(sup + sub) / 2 for sup, sub in zip(lst_bboxes[name]['min_bound'], lst_bboxes[name]['max_bound'])]
            ]
            res = ICP_process(conf, bbox_offset, False)
            if res == -1:
                lst_to_remove.append(name)

        # remove samples that have less than the minimum number of points
        for name in lst_to_remove:
            del lst_tiles_to_process[name]
            del lst_tiles_to_process_path[name]
            del lst_tiles_to_process_res[name]

        # merge results
        merge_results_from_list(
            lst_result_paths=lst_tiles_to_process_res.values(),
            src_res_merged=src_final_res,
            crs=conf.data.crs,
            verbose=conf.args.verbose,
            )

        # save config
        shutil.copyfile(
                './config/one_file.yaml',
                os.path.join(src_final_res, 'config.yaml')
            )
        
        # delete temp folder and files
        shutil.rmtree(src_temp_folder)
        for file_src in files_to_remove:
            os.delete(file_src)
    else:
        ICP_process(conf, None, verbose)

if __name__ == "__main__": 
    conf = OmegaConf.load("./config/one_file.yaml")
    one_file(conf, conf.args.verbose)
