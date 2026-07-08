import os
import numpy as np
import open3d as o3d
import laspy
from time import time
from plyfile import PlyData
if __name__ != "__main__":
    from src.quadnode import QuadNode
import warnings


def read_pc_with_cat_timming(src_pc, list_cat_to_remove):
    ext = os.path.splitext(src_pc)[1].lower()
    if ext in ['.las', '.laz']:
        pc = laspy.read(src_pc)
        mask = np.ones(len(pc), dtype=np.bool_)
        Classification = getattr(pc, "classification")
        for val in list_cat_to_remove:
            mask[Classification == val] = False
        pc.points = pc.points[mask]
    else:
        raise ValueError(f"The pointcloud is not of type LAS or LAZ: {src_pc}")

    return pc


def read_ply_with_scalars(ply_path):
    """
    Read a PLY file and return an Open3D point cloud + a dict of scalar fields.
    """
    
    plydata = PlyData.read(ply_path)
    vertex = plydata['vertex']
    
    # Extract xyz
    x = np.array(vertex['x'])
    y = np.array(vertex['y'])
    z = np.array(vertex['z'])
    xyz = np.stack([x, y, z], axis=1)
    
    # Build Open3D point cloud
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(xyz)
    
    # Extract colors if available
    if all(c in vertex.data.dtype.names for c in ('red', 'green', 'blue')):
        r = np.array(vertex['red'], dtype=np.float64) / 255.0
        g = np.array(vertex['green'], dtype=np.float64) / 255.0
        b = np.array(vertex['blue'], dtype=np.float64) / 255.0
        pc.colors = o3d.utility.Vector3dVector(np.stack([r, g, b], axis=1))
    
    # Extract all scalar fields (scalar_* prefix)
    scalars = {}
    for name in vertex.data.dtype.names:
        if name.startswith('scalar_'):
            key = name[len('scalar_'):]  # strip prefix for cleaner access
            scalars[key] = np.array(vertex[name])
    
    return pc, scalars


def compute_planarity(points):
    """
    Returns planarity in [0, 1]. Close to 1 = flat plane. Close to 0 = complex geometry.
    Based on eigenvalues of the covariance matrix.
    """
    if len(points) < 3:
        return 1.0
    
    cov = np.cov(points.T)
    eigenvalues = np.sort(np.linalg.eigvalsh(cov))  # ascending: e0 <= e1 <= e2
    e0, e1, e2 = eigenvalues

    # total = e0 + e1 + e2 + 1e-10
    planarity = (e1 - e0) / e2  # high when e0 ≈ 0 and e1 ≈ e2

    return planarity


def compute_bbox(boundaries):
    # min_bound, max_bound = boundaries.get_min_bound(), boundaries.get_max_bound()
    minx, miny, minz = boundaries['min_bound']
    maxx, maxy, maxz = boundaries['max_bound']
    spanx = (maxx-minx) / 2
    spany = (maxy-miny) / 2
    bboxes = []
    for i in range(2):
        for j in range(2):
            x0 = minx + i * spanx
            y0 = miny + j * spany
            x1 = x0 + spanx
            y1 = y0 + spany
            # bboxes.append(o3d.geometry.AxisAlignedBoundingBox((x0, y0, minz), (x1, y1, maxz)))
            bboxes.append({
                'min_bound': [x0, y0, minz],
                'max_bound': [x1, y1, maxz],
            })
    return bboxes


def points_in_bbox(xyz_src, xyz_tgt, node, bbox):
    """Return indices of points inside bbox. xyz: Nx3 array, indices: subset indices."""
    # min_b = bbox.get_min_bound()
    # max_b = bbox.get_max_bound()
    min_b = np.array(bbox['min_bound'])
    max_b = np.array(bbox['max_bound'])
    # span = np.max([max_b - min_b, np.ones(min_b.shape) * 1000/2**5], axis=0)[0]
    span = max_b[0] - min_b[0]
    min_b_w_neigh = min_b - span
    max_b_w_neigh = max_b + span

    pts_src = xyz_src[node.indices_src]
    pts_tgt = xyz_tgt[node.indices_tgt]

    # compute points in source
    mask_src = (
        (pts_src[:, 0] >= min_b[0]) & (pts_src[:, 0] < max_b[0]) &
        (pts_src[:, 1] >= min_b[1]) & (pts_src[:, 1] < max_b[1])
    )
    mask_tgt = (
        (pts_tgt[:, 0] >= min_b[0]) & (pts_tgt[:, 0] < max_b[0]) &
        (pts_tgt[:, 1] >= min_b[1]) & (pts_tgt[:, 1] < max_b[1])
    )
    mask_tgt_neigh = (
        (pts_tgt[:, 0] >= min_b_w_neigh[0]) & (pts_tgt[:, 0] < max_b_w_neigh[0]) &
        (pts_tgt[:, 1] >= min_b_w_neigh[1]) & (pts_tgt[:, 1] < max_b_w_neigh[1])
    )

    return node.indices_src[mask_src], node.indices_tgt[mask_tgt], node.indices_tgt[mask_tgt_neigh]


def build_quadtree(
        xyz_src, xyz_tgt, parent, bbox, 
        indices_src, indices_tgt, indices_tgt_neigh, 
        level, min_tile_size, min_points, max_area, is_anthropic=False
        ):
    """Recursively build quadtree based on point density."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        center = np.mean(xyz_src[indices_src], axis=0)
    node = QuadNode(bbox, indices_src, indices_tgt, indices_tgt_neigh, center, level, parent, is_anthropic)
    # node.planarity = compute_planarity(xyz_src[indices_src])

    # stopping conditions
    area = ((bbox['max_bound'][0] - bbox['min_bound'][0]) * (bbox['max_bound'][1] - bbox['min_bound'][1])) / 1e6
    tile_size = np.min((np.array(bbox['max_bound']) - np.array(bbox['min_bound']))[0:2])
    if area <= max_area:
        if is_anthropic:
            tile_len = np.max([len(indices_src), len(indices_tgt)])
            if tile_len < min_points:
                return None
            
            if len(indices_src) < 0.1 * len(indices_tgt) and (len(indices_tgt) < min_points or tile_size / 2 < min_tile_size):
                node.anthropic_state = 1
                return node
            elif len(indices_tgt) < 0.1 * len(indices_src) and (len(indices_src) < min_points or tile_size / 2 < min_tile_size):
                node.anthropic_state = 2
                return node
        else:
            tile_len = np.min([len(indices_src), len(indices_tgt)])
            if tile_len < min_points:
                return node

    sub_bboxes = compute_bbox(bbox)

    tile_size = np.min((np.array(sub_bboxes[0]['max_bound']) - np.array(sub_bboxes[0]['min_bound']))[0:2])
    if tile_size > min_tile_size:
        for subbbox in sub_bboxes:

            # Test if children are small enough to be process
            subarea = ((bbox['max_bound'][0] - bbox['min_bound'][0]) * (bbox['max_bound'][1] - bbox['min_bound'][1])) / 1e6
            if subarea <= max_area:
                sub_idx_src, sub_idx_tgt, sub_idx_tgt_neigh = points_in_bbox(xyz_src, xyz_tgt, node, subbbox)
            else:
                sub_idx_src, sub_idx_tgt, sub_idx_tgt_neigh = None, None, None

            child = build_quadtree(
                xyz_src, xyz_tgt, node, subbbox, sub_idx_src, sub_idx_tgt, sub_idx_tgt_neigh,
                level + 1, min_tile_size, min_points, is_anthropic,
            )
            node.children.append(child)

        if node.children:
            node.is_leaf = False

    return node


def extract_subcloud(pc, indices):
    """Return a sub pointcloud from indices (including normals if available)."""
    
    sub_pc = o3d.geometry.PointCloud()

    pts = np.asarray(pc.points)
    sub_pc.points = o3d.utility.Vector3dVector(pts[indices])

    # Copy normals if they exist
    if pc.has_normals():
        normals = np.asarray(pc.normals)
        sub_pc.normals = o3d.utility.Vector3dVector(normals[indices])

    return sub_pc


def run_icp_on_tree(node, pc_source, pc_target, src_res, args, time_subclouds_creation, time_icp, time_subclouds_saving, mode='ground'):
    """Traverse tree and run ICP on each node."""
    if node == None:
        return

    x,y,_ = node.bbox['min_bound']

    time_sub_0 = time()
    pc_tgt_neigh = extract_subcloud(pc_target, node.indices_tgt_neigh)
    pc_tgt = extract_subcloud(pc_target, node.indices_tgt)
    pc_src = extract_subcloud(pc_source, node.indices_src)
    time_subclouds_creation.append(time() - time_sub_0)

    if len(pc_src.points) == 0 or len(pc_tgt.points) == 0:
        return
    # save source and target tile if wanted:
    if args.do_output_transformed and args.output_level in [-1, node.level]:
        time_sub_0 = time()
        src_file = os.path.join(src_res, f'alligned_pc_lvl={node.level}_x={x}_y={y}_target.ply')
        o3d.io.write_point_cloud(src_file, pc_tgt)
        src_file = os.path.join(src_res, f'alligned_pc_lvl={node.level}_x={x}_y={y}_source.ply')
        o3d.io.write_point_cloud(src_file, pc_src)
        time_subclouds_saving.append(time() - time_sub_0)

    # choose method
    method = None
    if args.method == 'pointtopoint':
        method = o3d.pipelines.registration.TransformationEstimationPointToPoint()
    elif args.method == 'pointtoplane':
        method = o3d.pipelines.registration.TransformationEstimationPointToPlane()
    elif args.method == 'gicp':
        method = o3d.pipelines.registration.TransformationEstimationForGeneralizedICP()
    elif args.method == 'mix':
        if mode == 'ground':
            method = o3d.pipelines.registration.TransformationEstimationPointToPlane()
        else:
            method = o3d.pipelines.registration.TransformationEstimationPointToPoint()
    else:
        raise ValueError(f"The given method is wrong!\n\tGiven: {args.method}\n\tAccepted: [pointtopoint, pointtoplane]")

    pretransform = node.parent.global_transform if node.parent != None else np.eye(4)
    pc_src.transform(pretransform)

    # find corresponding max_correspondence
    max_correspondence = args.max_correspondence
    if isinstance(max_correspondence, list):
        if node.level >= len(max_correspondence):
            raise AttributeError(f"The list of values for max_correspondence is too short to match the level {node.level} of the tree!")
        max_correspondence = max_correspondence[node.level]

    time_icp0 = time()

    if args.method in ['pointtopoint', 'pointtoplane', 'mix']:
        reg = o3d.pipelines.registration.registration_icp(
            pc_src,
            pc_tgt_neigh,
            max_correspondence_distance=max_correspondence,
            init=np.eye(4),
            estimation_method=method,
            criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
                max_iteration=args.max_iteration,           # default: 30
                relative_fitness=args.threshold,            # default: 1e-6
                relative_rmse=args.threshold                # default: 1e-6
            )
        )
    else:   # gicp
        reg = o3d.pipelines.registration.registration_generalized_icp(
            pc_src,
            pc_tgt_neigh,
            max_correspondence_distance=max_correspondence,
            init=np.eye(4),
            estimation_method=method,
            criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
                max_iteration=args.max_iteration,           # default: 30
                relative_fitness=args.threshold,            # default: 1e-6
                relative_rmse=args.threshold                # default: 1e-6
            )
        )

    time_icp.append(time() - time_icp0)

    node.fitness = reg.fitness
    node.inlier_rmse = reg.inlier_rmse
    node.local_transform = reg.transformation
    node.global_transform = reg.transformation @ pretransform

    # save transformed tile if wanted:
    if args.do_output_transformed and args.output_level in [-1, node.level]:
        time_sub_0 = time()
        src_file = os.path.join(src_res, f'alligned_pc_lvl={node.level}_x={x}_y={y}_pretransformed.ply')
        o3d.io.write_point_cloud(src_file, pc_src)
        pc_src.transform(reg.transformation)
        src_file = os.path.join(src_res, f'alligned_pc_lvl={node.level}_x={x}_y={y}_transformed.ply')
        o3d.io.write_point_cloud(src_file, pc_src)
        time_subclouds_saving.append(time() - time_sub_0)

    # erase indices for storage
    node.indices_src = None
    node.indices_tgt = None
    node.indices_tgt_neigh = None

    for child in node.children:
        run_icp_on_tree(child, pc_source, pc_target, src_res, args, time_subclouds_creation, time_icp, time_subclouds_saving, mode=mode)


def filter_las_by_classification(las, classification_value, mode):
    """Filter laspy object by classification and return an Open3D point cloud."""
    assert mode in ['keep', 'remove']

    # if "classification" not in vars(las):
    if "classification" not in las.point_format.dimension_names:
        mask = np.ones(len(las), dtype=np.bool)
    elif len(set(las.classification)) == 1:
        mask = np.ones(len(las), dtype=np.bool)
    elif mode == 'keep':
        if isinstance(classification_value, list):
            mask = np.array([x in [classification_value] for x in las.classification])
        else:
            mask = las.classification == classification_value
    elif mode == 'remove':
        # remove all elements of list
        if isinstance(classification_value, list):
            mask = np.array([x not in [classification_value] for x in las.classification])
        else:
            mask = las.classification != classification_value
    else:
        mask = np.ones(len(las), dtype=np.bool)

    filtered_points = las.points[mask]
    
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(
        np.stack([filtered_points['X'] * las.header.scale[0] + las.header.offset[0],
                  filtered_points['Y'] * las.header.scale[1] + las.header.offset[1],
                  filtered_points['Z'] * las.header.scale[2] + las.header.offset[2]], axis=1)
    )
    
    return pc


def node_to_list(node):
    if node.is_leaf:
        return [node]
    else:
        list_of_nodes = []
        for child in node.children:
            if child != None:
                sub_list = node_to_list(child)
                list_of_nodes.append(sub_list)
        list_of_nodes = [x for row in list_of_nodes for x in row]
        list_of_nodes.append(node)
        return list_of_nodes


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
    

def trim_branch(node):
    if node == None:
        return
    
    # Detach from parent
    if node.parent is not None and node in node.parent.children:
        node.parent.children.remove(node)
        if node.parent.children == []:
            node.parent.is_leaf = True

    if node.children != []:
        for child in node.children:
            trim_branch(child)

    # Break all references so pickle can't follow them
    node.parent = None
    node.children = []


if __name__ == "__main__":
    a = np.array([0, 1, 2, 1, 0])
    mask = [x not in [0, 1] for x in a]
    print(mask)