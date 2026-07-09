import os
import sys
import numpy as np
from tqdm import tqdm
from plyfile import PlyData, PlyElement
from pyproj import Transformer, CRS
import laspy
import open3d as o3d
import traceback


class Convertions:
    @staticmethod
    def convert_laz_to_las(in_laz, out_las, offsets=[0,0,0], verbose=True, **kwargs):
        """
        Converts a LAZ file to an uncompressed LAS file.

        Args:
            - in_laz (str): Path to the input .laz file.
            - out_las (str): Path to the output .las file.
            - verbose (bool, optional): Whether to print confirmation of the saved file. Defaults to True.

        Returns:
            - None: Saves the converted .las file.
        """

        las = laspy.read(in_laz)
        las = laspy.convert(las)
        las.write(out_las)
        if verbose:
            print(f"LAS file saved in {out_las}")

    @staticmethod
    def convert_las_to_laz(in_las, out_laz, offsets=[0,0,0], verbose=True, **kwargs):
        """
        Converts a LAZ file to an uncompressed LAS file.

        Args:
            - in_laz (str): Path to the input .laz file.
            - out_las (str): Path to the output .las file.
            - verbose (bool, optional): Whether to print confirmation of the saved file. Defaults to True.

        Returns:
            - None: Saves the converted .las file.
        """

        las = laspy.read(in_las)
        las = laspy.convert(las)
        las.write(out_laz)
        if verbose:
            print(f"LAS file saved in {out_laz}")

    @staticmethod
    def convert_laz_to_txt(in_laz, out_txt, offsets=[0,0,0], verbose=True, **kwargs):
        laz = laspy.read(in_laz)
        list_dims = ['x', 'y', 'z','intensity']
        points = np.concatenate([np.array(getattr(laz, x)).reshape(-1,1) for x in list_dims], axis=1)
        points[:, 0] -= offsets[0]
        points[:, 1] -= offsets[1]
        points[:, 2] -= offsets[2]
        points[:, 3] =  points[:, 3] / 65535 * 255

        # Write to a txt file
        with open(out_txt, "w") as f:
            precision = int(np.log10(1/laz.header.scales[0]))
            np.savetxt(f, points, fmt=f"%.{precision}f,%.{precision}f,%.{precision}f,%d")

    @staticmethod
    def convert_txt_to_laz(in_txt, out_laz, offsets=[0,0,0], verbose=True, **kwargs):
        # Load the txt
        data = np.loadtxt(in_txt, delimiter=',')

        if data.ndim == 1:
            data = data.reshape(1, -1)

        # Create a LAS file with a point format that supports intensity + extra dims
        header = laspy.LasHeader(point_format=3, version="1.4")
        header.scales = np.array([0.0001, 0.0001, 0.0001])
        header.offsets = np.array(offsets)
        las = laspy.LasData(header)

        # Assign coordinates (laspy expects scaled ints internally)
        las.x = data[:, 0] + offsets[0]
        las.y = data[:, 1] + offsets[1]
        las.z = data[:, 2] + offsets[2]
        las.intensity = data[:, 3] / 255 * 65535

        # Save the result
        las.write(out_laz)

        if verbose:
            print(f"Saved LAZ with {len(las)} points to: {out_laz}")
            print("Dimensions:", las.point_format.dimension_names)

    @staticmethod
    def convert_laz_to_npz(laz_path: str, output_path: str = None, verbose=False, **kwargs):
        """
        Convert a .laz or .las file to a .npz file.
        Saves x, y, z coordinates and all other dimensions from the point cloud.
        """

        las = laspy.read(laz_path)

        if output_path is None:
            output_path = os.path.splitext(laz_path)[0] + ".npz"

        data_dict = {}

        # --- Standard coordinates ---
        data_dict["x"] = las.x.copy()
        data_dict["y"] = las.y.copy()
        data_dict["z"] = las.z.copy()

        # --- All other dimensions (including extra dimensions) ---
        for dim in las.point_format.dimensions:
            name = dim.name
            if name in ("X", "Y", "Z"):  
                continue  # skip raw scaled ints
            if name.lower() in ("x", "y", "z"):  
                continue

            try:
                arr = las[name].copy()
                data_dict[name] = arr
            except Exception as e:
                print(f"⚠️ Could not load dimension '{name}': {e}")

        # Save
        np.savez_compressed(output_path, **data_dict)

        if verbose:
            print(f"NPZ saved to: {output_path}")
            print(f"Saved fields: {list(data_dict.keys())}")

    @staticmethod
    def convert_npz_to_laz(npz_path: str, output_path: str = None, verbose = False, **kwargs):
        """
        Convert a .npz file containing point cloud data to a .laz file.
        Automatically detects coordinate field names or combined xyz arrays.
        """
        data = np.load(npz_path)
        keys = data.files

        # Try to detect coordinate arrays
        if {"x", "y", "z"}.issubset(keys):
            x, y, z = data["x"], data["y"], data["z"]
        elif "coords" in keys and data["coords"].shape[1] >= 3:
            x, y, z = data["coords"][:, 0], data["coords"][:, 1], data["coords"][:, 2]
        elif "points" in keys and data["points"].shape[1] >= 3:
            x, y, z = data["points"][:, 0], data["points"][:, 1], data["points"][:, 2]
        else:
            raise ValueError(f"Could not find x,y,z or a combined coordinate array in {npz_path}")

        # Prepare output path
        if output_path is None:
            output_path = os.path.splitext(npz_path)[0] + ".laz"

        header = laspy.LasHeader(point_format=3, version="1.2")
        las = laspy.LasData(header)
        las.x, las.y, las.z = x, y, z

        # Add any other attributes as extra dimensions
        for key in keys:
            if key in ("x", "y", "z", "coords", "points"):
                continue
            arr = data[key]
            if len(arr) == len(las.x):
                try:
                    las.add_extra_dim(laspy.ExtraBytesParams(name=key, type=arr.dtype))
                    setattr(las, key, arr)
                except Exception as e:
                    print(f"⚠️ Skipping attribute '{key}': {e}")

        las.write(output_path)
        if verbose:
            print(f"LAZ file saved in {output_path}")

    @staticmethod
    def convert_las_to_ply(las_path, output_path, use_color=True, verbose=False, **kwargs):
        las = laspy.read(las_path)

        x = np.array(las.x, dtype=np.float32)
        y = np.array(las.y, dtype=np.float32)
        z = np.array(las.z, dtype=np.float32)

        has_color = use_color and all(
            c in las.point_format.dimension_names for c in ("red", "green", "blue")
        )

        # Fields to skip (handled separately)
        skip_fields = {"x", "y", "z", "X", "Y", "Z"}
        if has_color:
            skip_fields.update({"red", "green", "blue"})

        # Collect scalar fields
        scalar_fields = []
        for name in las.point_format.dimension_names:
            if name in skip_fields:
                continue
            values = np.array(getattr(las, name), dtype=np.float32)
            scalar_fields.append((f"scalar_{name}", values))

        # Build dtype and data
        dtype = [("x", np.float32), ("y", np.float32), ("z", np.float32)]
        arrays = [x, y, z]

        if has_color:
            r = (las.red / 65535.0 * 255).astype(np.uint8)
            g = (las.green / 65535.0 * 255).astype(np.uint8)
            b = (las.blue / 65535.0 * 255).astype(np.uint8)
            dtype += [("red", np.uint8), ("green", np.uint8), ("blue", np.uint8)]
            arrays += [r, g, b]
        print([x[0] + "\n" for x in scalar_fields])
        for name, values in scalar_fields:
            dtype.append((name, np.float32))
            arrays.append(values)

        vertex_data = np.array(list(zip(*arrays)), dtype=dtype)

        el = PlyElement.describe(vertex_data, "vertex")
        PlyData([el], text=False).write(output_path)

        if verbose:
            scalar_names = [n for n, _ in scalar_fields]
            print(f"Saved to {output_path}")
            print(f"  Points   : {len(x)}")
            print(f"  Color    : {has_color}")
            print(f"  Scalars  : {scalar_names}")

    @staticmethod
    def convert_laz_to_ply(laz_path, output_path, use_color=True, verbose=False, **kwargs):
        Convertions.convert_las_to_ply(laz_path, output_path, use_color, verbose)
        # """
        # Convert a .laz or .las file to .ply format.

        # Parameters:
        #     laz_path (str): Path to the input .laz/.las file.
        #     output_path (str): Path to the output .ply file.
        #     use_color (bool): Whether to include RGB color if available.

        # Returns:
        #     None
        # """
        # # Read the LAS/LAZ file
        # las = laspy.read(laz_path)

        # # Extract coordinates
        # x = las.x
        # y = las.y
        # z = las.z

        # # Prepare base vertex array
        # vertices = [("x", np.float32), ("y", np.float32), ("z", np.float32)]

        # if use_color and all(hasattr(las, c) for c in ("red", "green", "blue")):
        #     # Normalize RGB to 0–255
        #     r = (las.red / np.max(las.red) * 255).astype(np.uint8)
        #     g = (las.green / np.max(las.green) * 255).astype(np.uint8)
        #     b = (las.blue / np.max(las.blue) * 255).astype(np.uint8)
        #     vertices += [("red", np.uint8), ("green", np.uint8), ("blue", np.uint8)]
        #     vertex_data = np.array(list(zip(x, y, z, r, g, b)), dtype=vertices)
        # else:
        #     vertex_data = np.array(list(zip(x, y, z)), dtype=vertices)

        # # Create and write PLY file
        # el = PlyElement.describe(vertex_data, "vertex")
        # PlyData([el], text=True).write(output_path)

        # if verbose:
        #     print(f"LAZ file saved in {output_path}")

    @staticmethod
    def convert_ply_to_laz(ply_path, output_path=None, verbose=False, **kwargs):
        """
        Convert a .ply file (with optional color and extra attributes) to a .laz file.

        Parameters:
            ply_path (str): Path to the input .ply file.
            output_path (str, optional): Path to the output .laz file. If None, replaces .ply with .laz.
            verbose (bool): Whether to print info during processing.

        Returns:
            str: Path to the output .laz file.
        """
        # Default output name
        if output_path is None:
            output_path = os.path.splitext(ply_path)[0] + ".laz"

        # Read the PLY file
        plydata = PlyData.read(ply_path)
        vertex = plydata["vertex"].data

        # Extract main coordinates
        x = np.asarray(vertex["x"], dtype=np.float64)
        y = np.asarray(vertex["y"], dtype=np.float64)
        z = np.asarray(vertex["z"], dtype=np.float64)

        # Create LAS header (format 3 allows RGB)
        header = laspy.LasHeader(point_format=3, version="1.4")
        las = laspy.LasData(header)
        las.x, las.y, las.z = x, y, z

        # --- Handle colors ---
        color_fields = {"red", "green", "blue"}
        if color_fields.issubset(vertex.dtype.names):
            las.red = np.asarray(vertex["red"], dtype=np.uint16)
            las.green = np.asarray(vertex["green"], dtype=np.uint16)
            las.blue = np.asarray(vertex["blue"], dtype=np.uint16)
        elif {"r", "g", "b"}.issubset(vertex.dtype.names):
            las.red = np.asarray(vertex["r"], dtype=np.uint16)
            las.green = np.asarray(vertex["g"], dtype=np.uint16)
            las.blue = np.asarray(vertex["b"], dtype=np.uint16)

        # --- Add extra dimensions ---
        reserved = {"x", "y", "z", "red", "green", "blue", "r", "g", "b"}
        extra_fields = [f for f in vertex.dtype.names if f not in reserved]

        for field in extra_fields:
            data = np.asarray(vertex[field])
            dtype = data.dtype

            # Determine appropriate LAS type
            if np.issubdtype(dtype, np.integer):
                las.add_extra_dim(laspy.ExtraBytesParams(name=field, type=data.dtype))
                las[field] = data
            elif np.issubdtype(dtype, np.floating):
                las.add_extra_dim(laspy.ExtraBytesParams(name=field, type=np.float32))
                las[field] = data.astype(np.float32)
            else:
                if verbose:
                    print(f"⚠️ Skipping non-numeric field '{field}' ({dtype})")

        # --- Write file ---
        las.write(output_path)
        if verbose:
            print(f"✅ Wrote LAZ file: {output_path}")
            print(f"   → Points: {len(x)} | Extra dims: {extra_fields}")

    @staticmethod
    def convert_pcd_to_laz(in_pcd, out_laz, verbose=True, **kwargs):
        """
        Converts a PCD file to a compressed LAZ file using open3d + laspy + pyproj.
        Preserves additional fields like classification.
        Args:
            - in_pcd (str): Path to the input .pcd file.
            - out_laz (str): Path to the output .laz file.
            - verbose (bool, optional): Whether to print confirmation. Defaults to True.
        Returns:
            - None
        """
        # --------------------------------
        # Parse PCD header to find fields
        # --------------------------------
        fields = []
        n_points = 0
        data_type = 'ascii'
        header_end = 0

        with open(in_pcd, 'rb') as f:
            for line in f:
                header_end += len(line)
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str.startswith('FIELDS'):
                    fields = line_str.split()[1:]
                elif line_str.startswith('POINTS'):
                    n_points = int(line_str.split()[1])
                elif line_str.startswith('DATA'):
                    data_type = line_str.split()[1]
                    break

        # --------------------------------
        # Read XYZ with open3d
        # --------------------------------
        pc = o3d.io.read_point_cloud(in_pcd)
        xyz = np.asarray(pc.points)

        # --------------------------------
        # Read extra fields manually
        # --------------------------------
        extra_fields = {f: None for f in fields if f not in ('x', 'y', 'z')}

        if extra_fields:
            if data_type == 'ascii':
                data = np.loadtxt(in_pcd, comments=['#', 'V', 'F', 'S', 'W', 'P', 'D'], max_rows=n_points)
                for i, field in enumerate(fields):
                    if field in extra_fields:
                        extra_fields[field] = data[:, i]
            elif data_type == 'binary':
                # For binary PCD, read raw bytes after header
                with open(in_pcd, 'rb') as f:
                    f.seek(header_end)
                    raw = np.frombuffer(f.read(), dtype=np.float32)
                    n_fields = len(fields)
                    data = raw.reshape((n_points, n_fields))
                    for i, field in enumerate(fields):
                        if field in extra_fields:
                            extra_fields[field] = data[:, i]

        # --------------------------------
        # Reproject from EPSG:4326 to EPSG:2056
        # --------------------------------
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
        x, y, z = transformer.transform(xyz[:, 0], xyz[:, 1], xyz[:, 2])
        xyz = np.column_stack([x, y, z])

        # --------------------------------
        # Compute safe scale
        # --------------------------------
        offsets = xyz.min(axis=0)
        xyz_local = xyz - offsets
        max_range = xyz_local.max(axis=0).max()
        safe_scale = max(0.001, float(max_range) / 2e9) if max_range > 0 else 0.001

        # --------------------------------
        # Write LAZ
        # --------------------------------
        header = laspy.LasHeader(point_format=3, version="1.4")
        header.scales = [safe_scale, safe_scale, safe_scale]
        header.offsets = offsets
        header.add_crs(CRS.from_epsg(2056))

        las = laspy.LasData(header)
        las.x = xyz[:, 0]
        las.y = xyz[:, 1]
        las.z = xyz[:, 2]

        # Write classification as native LAS field if present
        if 'classification' in extra_fields and extra_fields['classification'] is not None:
            las.classification = extra_fields['classification'].astype(np.uint8)

        # Write any other extra fields as extra dims
        for field, values in extra_fields.items():
            if field == 'classification' or values is None:
                continue
            las.add_extra_dim(laspy.ExtraBytesParams(name=field, type=values.dtype))
            setattr(las, field, values)

        las.write(out_laz)

        if verbose:
            print(f"LAZ file saved in {out_laz}")
            print(f"  Points : {len(xyz)}")
            print(f"  Fields : {list(extra_fields.keys())}")


def convert_one_file(src_file_in, src_file_out, in_type, out_type, **kwargs):
    assert in_type in ['las', 'laz', 'txt', 'npz' 'ply', 'pcd']
    assert out_type in ['las', 'laz', 'txt', 'npz', 'ply']
    assert in_type != out_type

    if not hasattr(Convertions, f"convert_{in_type}_to_{out_type}"):
        print(f"No function for converting {in_type} into {out_type}!!")
        return
    try:
        _ = getattr(Convertions, f"convert_{in_type}_to_{out_type}")(src_file_in, src_file_out, verbose=False, **kwargs)
    except Exception as e:
        print(f"conversion from {in_type} to {out_type} for sample {src_file_in} failed")
        print(traceback.format_exc())
        pass


def convert_all_in_folder(src_folder_in, src_folder_out, in_type, out_type, offsets=[0,0,0], verbose=False, **kwargs):
    """
    Converts all files in a folder from one point cloud format to another.

    Args:
        - src_folder_in (str): Path to the input folder containing files to convert.
        - src_folder_out (str): Path to the output folder where converted files will be saved.
        - in_type (str): Input file type ('las', 'laz', 'npz', 'txt', 'ply' or 'pcd').
        - out_type (str): Output file type ('las', 'laz', 'npz', 'txt', 'ply' or 'pcd').
        - verbose (bool, optional): Whether to display a progress bar and detailed messages. Defaults to False.

    Returns:
        - None: Saves all converted files into the specified output folder.
    """
    
    assert in_type in ['las', 'laz', 'txt']
    assert out_type in ['las', 'laz', 'txt']
    assert in_type != out_type

    if not hasattr(Convertions, f"convert_{in_type}_to_{out_type}"):
        print(f"No function for converting {in_type} into {out_type}!!")
        return
    os.makedirs(src_folder_out, exist_ok=True)  # Ensure output folder exists
    files = [f for f in os.listdir(src_folder_in) if f.endswith(in_type)]
    for _, file in tqdm(enumerate(files), total=len(files), desc=f"Converting {in_type} in {out_type}", disable=verbose==False):
        file_out = file.split(in_type)[0] + out_type
        convert_one_file(os.path.join(src_folder_in, file), os.path.join(src_folder_out, file_out), in_type, out_type, offsets, **kwargs)


if __name__ == "__main__":
    if len(sys.argv) >= 5:
        src_folder_in = sys.argv[1]
        src_folder_out = sys.argv[2]
        in_type = sys.argv[3]
        out_type = sys.argv[4]
        verbose = False
        if len(sys.argv) == 6:
            if sys.argv[5].lower() == "true":
                verbose = True
        
        convert_all_in_folder(src_folder_in, src_folder_out, in_type, out_type, verbose)
    else:
        print("Missing arguments!")
        quit()