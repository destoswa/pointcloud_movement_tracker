from pathlib import Path
from osgeo import gdal


def build_vrt_and_cog(
    input_dir,
    vrt_path,
    cog_path,
):
    """Build a VRT from all TIFFs in a directory and convert it to a COG."""
    input_dir = Path(input_dir)

    tif_files = sorted(input_dir.glob("*.tif"))

    if not tif_files:
        raise RuntimeError(f"No TIFF files found in {input_dir}")

    print(f"Found {len(tif_files):,} TIFF files")

    # ------------------------------------------------------------------
    # 1. Build VRT
    # ------------------------------------------------------------------
    vrt_options = gdal.BuildVRTOptions(
        resolution="average",
        resampleAlg="nearest",
    )

    vrt = gdal.BuildVRT(
        str(vrt_path),
        [str(f) for f in tif_files],
        options=vrt_options,
    )

    if vrt is None:
        raise RuntimeError("Failed to create VRT")

    vrt.FlushCache()
    vrt = None

    print(f"VRT created: {vrt_path}")

    # ------------------------------------------------------------------
    # 2. Convert VRT -> COG
    # ------------------------------------------------------------------
    cog = gdal.Translate(
        str(cog_path),
        str(vrt_path),
        format="COG",
        creationOptions=[
            "COMPRESS=DEFLATE",
            "BLOCKSIZE=512",
            "OVERVIEWS=AUTO",
            "BIGTIFF=YES",
        ],
    )

    if cog is None:
        raise RuntimeError("Failed to create COG")

    cog.FlushCache()
    cog = None

    print(f"COG created: {cog_path}")


if __name__ == "__main__":
    build_vrt_and_cog(
        input_dir=r"F:\DEM\2015_Vaud\tiles",
        vrt_path=r"F:\DEM\2015_Vaud\DEM_2015_Vaud.vrt",
        cog_path=r"F:\DEM\2015_Vaud\DEM_2015_Vaud_cog.tif",
    )