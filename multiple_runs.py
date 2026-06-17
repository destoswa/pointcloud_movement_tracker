from omegaconf import OmegaConf
from copy import deepcopy
from process_one_tile import ICP_process


if __name__ == "__main__":
    conf = OmegaConf.load("./config/one_tile.yaml")
    list_configs = [
        {   # 18-24 gicp
            "data.src_pc1": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2018_2588-1169_2056_5728.las",
            "data.src_pc2": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2024_2588-1169_2056_5728.las",
            "data.src_res": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\18-24\2588-1169\gicp",
            "args.min_tile_size_ground": 7,
            "args.min_tile_size_anthropic": 7,
            "args.method": "gicp",
        },
        {   # 18-24 pointtopoint
            "data.src_pc1": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2018_2588-1169_2056_5728.las",
            "data.src_pc2": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2024_2588-1169_2056_5728.las",
            "data.src_res": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\18-24\2588-1169\pointtopoint",
            "args.min_tile_size_ground": 7,
            "args.min_tile_size_anthropic": 7,
            "args.method": "pointtopoint",
        },
        {   # 18-24 pointtoplane
            "data.src_pc1": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2018_2588-1169_2056_5728.las",
            "data.src_pc2": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2024_2588-1169_2056_5728.las",
            "data.src_res": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\18-24\2588-1169\pointtoplane",
            "args.min_tile_size_ground": 7,
            "args.min_tile_size_anthropic": 7,
            "args.method": "pointtoplane",
        },
        {   # 15-19 gicp
            "data.src_pc1": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_3_real_movement_artificial_spacing\all_tiles\2588_1169\laz\PC2015_2588_1169.laz",
            "data.src_pc2": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_3_real_movement_artificial_spacing\all_tiles\2588_1169\laz\PC2019_2588_1169.laz",
            "data.src_res": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\15-19\2588-1169\gicp",
            "args.min_tile_size_ground": 15,
            "args.min_tile_size_anthropic": 15,
            "args.method": "gicp",
        },
        {   # 15-19 pointtopoint
            "data.src_pc1": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_3_real_movement_artificial_spacing\all_tiles\2588_1169\laz\PC2015_2588_1169.laz",
            "data.src_pc2": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_3_real_movement_artificial_spacing\all_tiles\2588_1169\laz\PC2019_2588_1169.laz",
            "data.src_res": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\15-19\2588-1169\pointtopoint",
            "args.min_tile_size_ground": 15,
            "args.min_tile_size_anthropic": 15,
            "args.method": "pointtopoint",
        },
        {   # 15-19 pointtoplane
            "data.src_pc1": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_3_real_movement_artificial_spacing\all_tiles\2588_1169\laz\PC2015_2588_1169.laz",
            "data.src_pc2": r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_3_real_movement_artificial_spacing\all_tiles\2588_1169\laz\PC2019_2588_1169.laz",
            "data.src_res": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\15-19\2588-1169\pointtoplane",
            "args.min_tile_size_ground": 15,
            "args.min_tile_size_anthropic": 15,
            "args.method": "pointtoplane",
        },
        {   # 15-18 gicp
            "data.src_pc1": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\artificial_samples_for_mix\PC2015_2588_1169.laz",
            "data.src_pc2": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2018_2588-1169_2056_5728.las",
            "data.src_res": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\15-18\2588-1169\gicp",
            "args.min_tile_size_ground": 15,
            "args.min_tile_size_anthropic": 15,
            "args.method": "gicp",
        },
        {   # 15-18 pointtopoint
            "data.src_pc1": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\artificial_samples_for_mix\PC2015_2588_1169.laz",
            "data.src_pc2": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2018_2588-1169_2056_5728.las",
            "data.src_res": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\15-18\2588-1169\pointtopoint",
            "args.min_tile_size_ground": 15,
            "args.min_tile_size_anthropic": 15,
            "args.method": "pointtopoint",
        },
        {   # 15-18 pointtoplane
            "data.src_pc1": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\artificial_samples_for_mix\PC2015_2588_1169.laz",
            "data.src_pc2": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_4_real_movement_real_spacing\all_las_files\MNTB\swisssurface3d_2018_2588-1169_2056_5728.las",
            "data.src_res": "D:\GitHubProjects\Terranum_repo\pc_movement_tracking_dev\data\test_29_final_model_on_artif\15-18\2588-1169\pointtoplane",
            "args.min_tile_size_ground": 15,
            "args.min_tile_size_anthropic": 15,
            "args.method": "pointtoplane",
        },
    ]
    for config in list_configs:
        temp_conf = deepcopy(conf)
        for attribute, value in config.items():
            OmegaConf.select(temp_conf, attribute) = value
        
        ICP_process(temp_conf, True)
