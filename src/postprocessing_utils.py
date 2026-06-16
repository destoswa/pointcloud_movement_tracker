import numpy as np
import geopandas as gpd
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import pandas as pd
from src.quadnode import QuadNode
from math import atan2, asin, acos, degrees


def remove_A0(node, A0_inv):
    node.global_transform = np.linalg.matmul(node.global_transform, A0_inv)
    for child in node.children:
        if child != None:
            remove_A0(child, A0_inv)


def compute_translation(node):
    if node == None:
        return
    
    if node.anthropic_state <= 0:
        # Compute translation:
        center = np.vstack([node.center.reshape((3,1)), np.array([1])])
        translated = np.linalg.matmul(node.global_transform, center)
        diff = translated - center
        norm = float(np.linalg.norm(diff))
        norm2d = float(np.linalg.norm(diff[0:2]))
        direction = ((translated[0:2] - center[0:2]) / norm2d).squeeze(-1) if norm2d > 0 else np.zeros((2,1))

        node.metrics['pos_i'] = center[:3].squeeze(-1)
        node.metrics['pos_f'] = translated[:3].squeeze(-1)
        node.metrics['translation_x'] = direction[0]
        node.metrics['translation_y'] = direction[1]
        node.metrics['dx'] = float(diff[0][0])
        node.metrics['dy'] = float(diff[1][0])
        node.metrics['dz'] = float(diff[2][0])
        node.metrics['Disp2D'] = norm2d
        node.metrics['Disp3D'] = norm
        node.metrics['movement_vector'] = diff[0:3]
    else:
        node.metrics['pos_i'] = None
        node.metrics['pos_f'] = None
        node.metrics['translation_x'] = 0
        node.metrics['translation_y'] = 0
        node.metrics['dx'] = 0
        node.metrics['dy'] = 0
        node.metrics['dz'] = 0
        node.metrics['Disp2D'] = 0
        node.metrics['Disp3D'] = 0
        node.metrics['movement_vector'] = None

    for child in node.children:
        compute_translation(child)


def compute_rotation(node):
    if node == None:
        return
    
    if node.anthropic_state <= 0:
        # Compute translation at bbox center
        center = np.vstack([node.center.reshape((3,1)), np.array([1])])
        translated = np.linalg.matmul(node.global_transform, center)
        diff = translated - center
        dx, dy, dz = list(diff[:3].squeeze(-1))
        norm_3d = float(np.linalg.norm(diff[:3]))

        # Displacement direction: azimuth from North (Y axis), clockwise, in [0, 360°]
        DispDir = degrees(atan2(dx, dy)) % 360

        # Displacement plunge: angle below horizontal, in [0°, 90°]
        DispPlunge = degrees(asin(-dz / (norm_3d + 1e-10)))

        # Rotation axis direction: azimuth of the rotation axis projected on horizontal plane
        # Extract rotation axis from the transform
        R = node.global_transform[:3, :3]
        cos_angle = np.clip((np.trace(R) - 1) / 2, -1, 1)
        RotationAngle = degrees(np.arccos(cos_angle))

        # Rotation axis from skew-symmetric part of R
        axis = np.array([
            R[2, 1] - R[1, 2],
            R[0, 2] - R[2, 0],
            R[1, 0] - R[0, 1]
        ])
        axis_norm = np.linalg.norm(axis)
        RotationAxis = axis / axis_norm if axis_norm > 1e-10 else np.array([0, 0, 1])

        # Topple Direction
        topple_x = R[0, 2]
        topple_y = R[1, 2]
        ToppleDir = (degrees(atan2(topple_x, topple_y)) + 360) % 360

        # Topple Angle
        ToppleAngle = degrees(acos(R[2, 2]))

        node.metrics['DispDir'] = DispDir
        node.metrics['DispPlunge'] = DispPlunge
        node.metrics['ToppleDir'] = ToppleDir
        node.metrics['ToppleAngle'] = ToppleAngle
        node.metrics['RotationAngle'] = RotationAngle
        node.metrics['RotationAxis'] = RotationAxis
    else:
        node.metrics['DispDir'] = 0
        node.metrics['DispPlunge'] = 0
        node.metrics['ToppleDir'] = 0
        node.metrics['ToppleAngle'] = 0
        node.metrics['RotationAngle'] = 0
        node.metrics['RotationAxis'] = 0

    
    for child in node.children:
        compute_rotation(child)   


def trim_branch(node):
    if node == None:
        return
    if node.children != []:
        for child in node.children:
            trim_branch(child)
            
    # Detach from parent
    if node.parent is not None and node in node.parent.children:
        node.parent.children.remove(node)
        if node.parent.children == []:
            node.parent.is_leaf = True

    # Break all references so pickle can't follow them
    node.parent = None
    node.children = []


def detect_absurds(node, absurd_th):
    if node == None:
        return 0

    counter = 0

    # Compute local transform
    center = np.vstack([node.center.reshape((3,1)), np.array([1])])
    center = np.linalg.inv(node.local_transform) @ node.global_transform @ center
    translated = node.local_transform @ center
    diff = translated - center
    norm_local = float(np.linalg.norm(diff[:2, 0],0))   # norm 2D along 0xy

    # Apply changes if value absurd
    if norm_local > absurd_th and node.anthropic_state <= 0:# and node.is_leaf:
        counter += 1
        for child in node.children:
            trim_branch(child)
        if node.parent != None:
            for m in node.metrics.keys():
                node.metrics[m] = node.parent.metrics[m]
        node.is_absurd = True
        node.is_leaf = True
        node.children = []

    for child in node.children:
        counter += detect_absurds(child, absurd_th)
    return counter


def node_to_list(node, offset=(0,0,0)):
    attributes_name = []
    attributes_val = []
    for key, val in vars(node).items():
        if key in ['children', 'parent', 'local_transform'] or 'indices' in key:
            continue
        # if key == "center":
        #     attributes_name.append(key)
        #     attributes_val.append(val)
        #     for keyc, valc, of in zip(['x', 'y', 'z'], val, offset):
        #         attributes_name.append(keyc)
        #         attributes_val.append(valc + of)
        if key == "center":
            attributes_name.append(key)
            attributes_val.append(val)
            center = [
                (node.bbox['max_bound'][0] + node.bbox['min_bound'][0]) / 2,
                (node.bbox['max_bound'][1] + node.bbox['min_bound'][1]) / 2,
                val[2]]
            for keyc, valc, of in zip(['x', 'y', 'z'], center, offset):
                attributes_name.append(keyc)
                attributes_val.append(valc + of)
        elif key == 'metrics':
            for mkey, mval in val.items():
                if isinstance(mval, np.ndarray):
                    mval = list(mval)
                attributes_name.append(mkey)
                attributes_val.append(mval)
        else:
            attributes_name.append(key)
            attributes_val.append(val)
    return attributes_name, attributes_val


def compute_data_for_gpkg(node, offset):
    data, bbox_data = [], []
    if isinstance(node, QuadNode):
        # compute translation
        bbox_dict = node.bbox
        bbox_data.append([bbox_dict])
        data.append([node_to_list(node, offset)[1]])

        for child in node.children:
            if child != None:
                sub_data, sub_bbox_data = compute_data_for_gpkg(child, offset)
                data.append(sub_data)
                bbox_data.append(sub_bbox_data)

        # flattening
        data = [x for row in data for x in row]
        bbox_data = [x for row in bbox_data for x in row]
    elif isinstance(node, list):
        for el in node:
            # compute translation
            bbox_dict = el.bbox
            bbox_data.append(bbox_dict)
            data.append(node_to_list(el, offset)[1])
    else:
        raise ValueError("The node need to be a list of Quadtree nodes or the root of a Quadtree")
    
    return data, bbox_data


def clip_overlaps(gdf):
    """
    For each polygon, subtract all smaller polygons that overlap it.
    Smaller = smaller area.
    Returns a new GeoDataFrame with non-overlapping geometries.
    """
    gdf = gdf.copy()

    # compute area and sort such that smaller tiles appear on top of bigger ones
    gdf["area"] = gdf.geometry.area
    gdf = gdf.sort_values("area", ascending=False)

    new_geometries = []
    for i, row in gdf.iterrows():
        geom = row.geometry
        # Get all smaller polygons that overlap this one
        smaller = gdf[gdf.index > i]  # already sorted by area descending
        overlapping = smaller[smaller.geometry.intersects(geom)]
        
        if len(overlapping) > 0:
            # Subtract all smaller overlapping polygons
            union_smaller = unary_union(overlapping.geometry)
            geom = geom.difference(union_smaller)
        
        new_geometries.append(geom)

    gdf.geometry = new_geometries
    return gdf


def export_points_and_bboxes(data, columns, bbox_data, output_path, offset, do_clip_overlaps=False, to_export='both', layer_name='', crs="EPSG:2056"):

    df_points = pd.DataFrame(data, columns=columns)

    # --- Layer 2: BBoxes ---
    if to_export in ['boxes', 'both']:
        layer_name_sub = f"{layer_name}_tiles" if layer_name != '' else 'tiles'
        rows = []
        for bbox in bbox_data:
            minx, miny = bbox["min_bound"][0] + offset[0], bbox["min_bound"][1] + offset[1]
            maxx, maxy = bbox["max_bound"][0] + offset[0], bbox["max_bound"][1] + offset[1]
            poly = Polygon([
                (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny)
            ])
            rows.append(poly)

        gdf_bboxes = gpd.GeoDataFrame(df_points, geometry=rows, crs=crs)

        if do_clip_overlaps:
            gdf_bboxes = clip_overlaps(gdf_bboxes)  # reorders rows!

        gdf_bboxes.to_file(output_path, layer=layer_name_sub, driver="GPKG")

    # --- Layer 1: Points ---
    if to_export in ['points', 'both']:
        layer_name_sub = f"{layer_name}_centers" if layer_name != '' else 'centers'

        if do_clip_overlaps and to_export == 'both':
            # gdf_bboxes is reordered by clip_overlaps → use its index to reorder df_points
            df_points_reordered = df_points.iloc[gdf_bboxes.index].reset_index(drop=True)
            geometry_points = gdf_bboxes.geometry.centroid.reset_index(drop=True)
        else:
            df_points_reordered = df_points
            geometry_points = [Point(xy) for xy in zip(df_points["x"], df_points["y"])]

        gdf_points = gpd.GeoDataFrame(df_points_reordered, geometry=geometry_points, crs=crs)
        gdf_points.to_file(output_path, layer=layer_name_sub, driver="GPKG")


def tree_to_list(node, list_tot, list_per_level):
    list_tot.append(node)
    if node.level > len(list_per_level) - 1:
        list_per_level.append([])
    list_per_level[node.level].append(node)
    for child in node.children:
        if child != None:
            tree_to_list(child, list_tot, list_per_level)


def find_node(node, id):
    if node.id == id:
        return node
    else:
        for child in node.children:
            if child != None:
                res = find_node(child, id)
                if res != None:
                    return res
        return


def postprocessing(root, src_out_gpkg, offset, to_keep, absurd_dist=5, suffixe='', verbose=False):
    # prepare paths
    src_out_gpkg = src_out_gpkg.split('.gpkg')[0] + f"_{suffixe}.gpkg"
    src_out_gpkg_leaves = src_out_gpkg.split('.gpkg')[0] + f"_leaves.gpkg"
    src_out_gpkg_layers_tiles = src_out_gpkg.split('.gpkg')[0] + f"_layers_tiles.gpkg"
    src_out_gpkg_layers_centers = src_out_gpkg.split('.gpkg')[0] + f"_layers_centers.gpkg"

    # store nodes in a list
    list_nodes, list_nodes_per_level = [], []
    tree_to_list(root, list_nodes, list_nodes_per_level)

    # Compute metrics:
    compute_translation(root)
    compute_rotation(root)

    # Detect absurd values
    original_len = len(root)
    counter = detect_absurds(root, absurd_dist)

    if verbose:
        print(f"Number of absurd values: {counter} ({np.round(counter/original_len*100, 2)}%)")

    # Gather data for GPKG
    data, bbox_data = compute_data_for_gpkg(root, offset)

    columns = node_to_list(root)[0]

    # Export all tiles
    if to_keep.full_tree:
        export_points_and_bboxes(
            data=data,
            bbox_data=bbox_data,
            columns=columns,
            output_path=src_out_gpkg,
            offset=offset,
            do_clip_overlaps=False,
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
                layer_name=f"Level {lvl}"
            )

            export_points_and_bboxes(
                data=data,
                bbox_data=bbox_data,
                columns=columns,
                output_path=src_out_gpkg_layers_centers,
                to_export='points',
                offset=offset,
                layer_name=f"Level {lvl}"
            )
