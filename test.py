import os
import numpy as np
import laspy
import open3d as o3d
from scipy.interpolate import griddata
from scipy.spatial import Delaunay
from time import time

def densify_pointcloud_optimized(pc, target_spacing=0.5, max_hole_dist=2.0, method='linear'):
    """
    Densify a sparse point cloud by interpolating missing ground points.
    Only adds points in holes, not where points already exist.
    
    Parameters:
        pc: o3d.geometry.PointCloud
        target_spacing: desired point spacing in meters
        max_hole_dist: minimum distance from existing points to be considered a hole
        method: interpolation method: 'linear', 'cubic' or 'nearest'
    """
    from scipy.interpolate import griddata
    from scipy.spatial import KDTree

    pts = pc.xyz
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]

    # Build regular grid at target spacing
    xmin, xmax = x.min(), x.max()
    ymin, ymax = y.min(), y.max()
    grid_x, grid_y = np.meshgrid(
        np.arange(xmin, xmax, target_spacing),
        np.arange(ymin, ymax, target_spacing)
    )
    grid_pts = np.column_stack([grid_x.ravel(), grid_y.ravel()])

    # --- OPTIMIZATION 1: subsample for KDTree ---
    # No need to build tree on 30M points — subsample to ~100k
    max_tree_pts = 100_000
    if len(pts) > max_tree_pts:
        idx = np.random.choice(len(pts), max_tree_pts, replace=False)
        tree_pts = pts[idx, :2]
    else:
        tree_pts = pts[:, :2]
    
    tree = KDTree(tree_pts)

    # --- OPTIMIZATION 2: batch query (fully vectorized) ---
    dists, _ = tree.query(grid_pts, workers=-1)  # workers=-1 = all CPU cores
    hole_mask = dists > max_hole_dist

    if hole_mask.sum() == 0:
        print("  No holes found")
        return pc

    # --- OPTIMIZATION 3: interpolate only on hole points ---
    # Subsample source points for interpolation too
    max_interp_pts = 200_000
    if len(pts) > max_interp_pts:
        idx = np.random.choice(len(pts), max_interp_pts, replace=False)
        interp_src = pts[idx]
    else:
        interp_src = pts

    hole_pts = grid_pts[hole_mask]
    grid_z = griddata(
        points=interp_src[:, :2],
        values=interp_src[:, 2],
        xi=hole_pts,
        method=method,
        fill_value=np.nan
    )

    # Remove NaN (outside convex hull)
    valid = ~np.isnan(grid_z)
    fill_pts = np.column_stack([
        hole_pts[valid, 0],
        hole_pts[valid, 1],
        grid_z[valid]
    ])

    all_pts = np.vstack([pts, fill_pts])
    pc_dense = o3d.geometry.PointCloud()
    pc_dense.points = o3d.utility.Vector3dVector(all_pts)

    print(f"  Added {valid.sum()} synthetic points to fill {hole_mask.sum()} holes")
    return pc_dense


def densify_pointcloud(pc, target_spacing=0.5, method='linear'):
    """
    Densify a sparse point cloud by interpolating missing ground points.
    
    Parameters:
        pc: o3d.geometry.PointCloud
        target_spacing: desired point spacing in meters
        method: 'linear', 'cubic' or 'nearest'
    """
    pts = np.asarray(pc.xyz)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]

    # Build regular grid at target spacing
    xmin, xmax = x.min(), x.max()
    ymin, ymax = y.min(), y.max()
    grid_x, grid_y = np.meshgrid(
        np.arange(xmin, xmax, target_spacing),
        np.arange(ymin, ymax, target_spacing)
    )

    # Interpolate Z values onto grid
    grid_z = griddata(
        points=np.column_stack([x, y]),
        values=z,
        xi=(grid_x, grid_y),
        method=method,
        fill_value=np.nan
    )

    # Remove NaN (areas outside convex hull)
    mask = ~np.isnan(grid_z)
    new_pts = np.column_stack([
        grid_x[mask],
        grid_y[mask],
        grid_z[mask]
    ])

    # Merge original + interpolated points
    all_pts = np.vstack([pts, new_pts])
    
    pc_dense = o3d.geometry.PointCloud()
    pc_dense.points = o3d.utility.Vector3dVector(all_pts)
    return pc_dense


def read_pc_with_cat_timming(src_pc, cat_field=None, list_cat_to_keep=[], use_cat=False):
    ext = os.path.splitext(src_pc)[1].lower()
    if ext in ['.las', '.laz']:
        pc = laspy.read(src_pc)
        print(len(pc.points))
        if use_cat and cat_field != None:
            classification = getattr(pc, cat_field)
            mask = np.zeros(len(pc), dtype=np.bool_)
            for val in list_cat_to_keep:
                mask[classification == val] = True
        else:
            mask = np.ones(len(pc), dtype=np.bool)
        pc.points = pc.points[mask]
    else:
        raise ValueError(f"The pointcloud is not of type LAS or LAZ: {src_pc}")

    return pc


if __name__ == "__main__":
    time_start = time()
    src_pc = r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_38_incomplete_movement\swisssurface3d_2018_2577-1143_2056_5728.las"
    cat_field = 'classification'
    list_cat_to_keep = [2, 6, 17, 26, 27]
    pc = read_pc_with_cat_timming(
        src_pc=src_pc, 
        cat_field=cat_field,
        list_cat_to_keep=list_cat_to_keep,
        use_cat=True,
    )
    print(len(pc.points))

    pc_dense = densify_pointcloud_optimized(pc)
    print(len(pc_dense.points))
    print("PROCESS DONE IN ", time() - time_start, "seconds")