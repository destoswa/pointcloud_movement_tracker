import requests
import os
from tqdm import tqdm
import csv

def download_older(url, year):
    # url = url.split(str(year))[0] + str(year - 1) + str(year).join(url.split(str(year))[1:])
    url = url.split('.copc')[0].split('.laz')[0]

    count_down = 0
    new_year = year - 1
    while count_down < 10:
        for ext in ['.copc.laz', '.las', '.laz', '.las.zip']:
            url_to_test = url.replace(str(year), str(new_year)) + ext
            # print(url_to_test)
            # url_to_test = f"https://data.geo.admin.ch/ch.swisstopo.swisssurface3d/swisssurface3d_{year - 1}_2563-1145/swisssurface3d_{year - 1}_2563-1145_2056_5728{ext}"

            if requests.get(url_to_test).status_code == 200:
                return url_to_test
        new_year -= 1
        count_down += 1
        
    print(f"Could not find an older tile ")
    return


def download():
    src_urls = r"D:\Terranum_SD\2_Projects\pc_movement_tracking\vaud_liens\liens_vaud_total.csv"
    src_dest = r"D:\GitHubProjects\Terranum_repo\pc_movement_tracking\data\test_16_vaud"
    with open(src_urls, newline='') as f:
        reader = csv.reader(f)
        list_urls = list(reader)
    list_urls = [x for row in list_urls for x in row]

    for _, url in tqdm(enumerate(list_urls), total=len(list_urls)):
        data = requests.get(url).content
        file_src = os.path.join(src_dest, url.split('/')[-1])
        with open(file_src, 'wb') as handler:
            handler.write(data)
        
        older_url = download_older(url, 2024)
        if older_url == None:
            continue
        
        data = requests.get(older_url).content
        file_src = os.path.join(src_dest, older_url.split('/')[-1])
        with open(file_src, 'wb') as handler:
            handler.write(data)


if __name__ == "__main__":
    pass