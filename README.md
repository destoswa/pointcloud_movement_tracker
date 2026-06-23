# TODO BEFORE THE END
- change path to repo when migrated to terranum


# Pointclouds movement tracker

## How to install
This pipeline was developped using python 3.9 and was tested successfully on python 3.11

1) Clone the repo on local\
  Open a terminal, cd your way to the desired location and type:
    ```
    git clone --depth=1 https://github.com/destoswa/pointcloud_movement_tracker
    ```
2) Create a virtual environment
    ```
    cd playground_segmentation
    python -m venv .venv
    ```
3) Activate environment
   1) On Windows
        ```
        .venv\Scripts\activate
        ```
    2) On Linux
        ```
        .venv\bin\activate
        ```
4) Install the libaries
    ```
    pip install -r requirements.txt
    ```

## Introduction
This project implements a Python pipeline for detecting and quantifying local surface displacements between two LiDAR point clouds acquired at different epochs, with an arbitrary precision. It is designed for geoscientific applications such as landslide monitoring, terrain deformation analysis, and rockfall detection, with native support for Swiss georeferenced data (LV95 / EPSG:2056).

## Algorithm + architecture
The core of the pipeline relies on an adaptive quadtree spatial decomposition combined with the Iterative Closest Point (ICP) algorithm from Open3D, allowing displacement to be estimated at multiple spatial resolutions simultaneously. For each tile of the quadtree, a local ICP registration is computed and the resulting transformation is decomposed into physically meaningful quantities: displacement direction, plunge, magnitude, topple direction, and rotation angle. Results are exported as GIS-compatible layers (GeoPackage) for direct visualization and analysis in QGIS, including heatmaps, vector fields, and labeled polygon tiles.

## How to use
Different scripts are available to process a single file, to rework the postprocessing or to automatically process a serie of files.

All those tasks are driven through .yaml files in the folder `config`

### Single pointcloud
To process a single file, you need to run the script `process_one_tile.py` at the root of the project. The corresponding config file is `config/one_tile.yaml` which contains all the parameters to drive the ICP processing and the postprocessing, which is done automatically after the main process.

### Multiple pointclouds (Production)
The task at hand can be quite big (multiple hundreds or tousands of files). To automate the processing of them, the script `production.py` systematically calls the `process_one_tile.py` script.

In order to process multiple regions, each pair of files (old, new) need to be identified upstream. To do that, a csv file with 3 columns is readen:
- _pc1_: the relative or absolute path to the old pointcloud
- _pc2_: the relative or absolute path to the new pointcloud
- _res_: the relative or absolute path to the location of the results

This process is driven through the config file `config/production.yaml`.

Since the creation of the csv file can be a tedious task, a script has been created to automatically create a the csv file based on two folders containing the pointcloud of the two different epochs. The corresponding parameters are in the file `config/production.yaml` in the section `preprocessing`.

### Postprocessing
The postprocessing should not be used that much since it is done by `process_one_tile.py` but if one wants to tweak some parameters of this stage, one can then run the file `postprocessing.py` at the root of the project, which is significantly faster than re-running the full processing of the two pointclouds.