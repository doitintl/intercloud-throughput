import itertools
import os
from typing import List

import geopy.distance

from clouds.clouds import CloudRegion, Cloud
from util import utils

coords_1 = (52.2296756, 21.0122287)
coords_2 = (52.406374, 16.9251681)
import csv

REGIONS: List[CloudRegion]
REGIONS = []


def get_regions_with_coords():
    global REGIONS

    if not REGIONS:

        fp = open(utils.root_dir() + os.sep + "locations.csv")
        rdr = csv.DictReader(filter(lambda row: row[0] != "#", fp))
        for row in rdr:

            lat_s = row.get("lat")
            long_s = row.get("long")
            if lat_s is not None and long_s is not None:
                lat = float(lat_s)
                long = float(long_s)
            else:
                lat = long = None

            REGIONS.append(
                CloudRegion(Cloud(row["cloud"]), row["region"], lat=lat, long=long)
            )
        fp.close()
    return REGIONS


def get_region_with_coords(region: CloudRegion) -> CloudRegion:
    if region.lat is not None and region.long is not None:
        return region
    matches = [r for r in get_regions_with_coords() if r == region]
    if not matches:
        raise ValueError(f"Cannot find {region}")
    else:
        assert len(matches) == 1, matches
    return matches[0]


def datacenter_distance(region1, region2):

    r1 = get_region_with_coords(region1)
    r2 = get_region_with_coords(region2)
    assert not [x for x in  [r1.lat, r1.long, r2.lat , r2.long] if x is None]            ,f"All regions should have coords {r1}, {r2}"
    coords_1 = (r1.lat, r1.long)
    coords_2 = (r2.lat, r2.long)
    ret = geopy.distance.distance(coords_1, coords_2).km
    return ret


if __name__ == "__main__":
    pairs = itertools.product(get_regions_with_coords(), get_regions_with_coords())
    for pair in pairs:
        print(pair, datacenter_distance(pair[0], pair[1]),"km")
