import re
from enum import Enum
from typing import Optional, Dict

import csv
import inspect
from util.utils import gcp_default_project
import itertools
import os
from typing import List, Optional

import geopy.distance

from util import utils


class Cloud(Enum):
    GCP = "GCP"
    AWS = "AWS"

    def __str__(self):
        return self.name


class CloudRegion:
    def __init__(
        self,
        cloud: Cloud,
        region_id: str,
        lat: float = None,
        long: float = None,
        gcp_project: Optional[str] = None,
    ):
        curframe = inspect.currentframe()
        calframe = inspect.getouterframes(curframe, 2)
        assert (
            calframe[1][3] == "get_regions"
        ), "Call this only in building the regions list"

        assert re.match(r"[a-z][a-z-]+\d$", region_id)
        assert (cloud == Cloud.GCP) == bool(gcp_project)

        self.lat = lat
        self.long = long
        self.cloud = cloud
        self.region_id = region_id
        self.gcp_project = gcp_project

    def script(self):
        return f"{utils.root_dir()}/scripts/{self.lowercase_cloud_name()}-launch.sh"

    def deletion_script(self):
        return f"{utils.root_dir()}/scripts/{self.lowercase_cloud_name()}-delete-instances.sh"

    def script_for_test_from_region(self):
        return f"{utils.root_dir()}/scripts/do-one-test-from-{self.lowercase_cloud_name()}.sh"

    def __repr__(self):
        return f"{self.cloud.name}{self.region_id}"

    def env(self) -> Dict[str, str]:
        envs = {
            Cloud.GCP: {"PROJECT_ID": self.gcp_project},
            Cloud.AWS: {"BASE_KEYNAME": "intercloudperfkey"},
        }
        return envs[self.cloud]

    def lowercase_cloud_name(self):
        return self.cloud.name.lower()

    def __eq__(self, other):
        return (
            self.region_id == other.region_id
            and self.cloud == other.cloud
            and self.gcp_project == other.gcp_project
        )


__REGIONS: List[CloudRegion]
__REGIONS = []


def get_regions(gcp_project: Optional[str]):
    """ "
    :param gcp_project is optional, if provided, will be used for GCP regions. Otherwise, built-in default will be used.
    """

    def gcp_proj(cloud_, gcp_project):
        if cloud_ == Cloud.GCP.name:
            if gcp_project:
                gcp_proj = gcp_project
            else:
                gcp_proj = gcp_default_project()
        else:
            gcp_proj = None
        return gcp_proj

    global __REGIONS

    if not __REGIONS:

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

            cloud_ = row["cloud"]

            __REGIONS.append(
                CloudRegion(
                    Cloud(cloud_),
                    row["region"],
                    lat,
                    long,
                    gcp_proj(cloud_, gcp_project),
                )
            )
        fp.close()
    return __REGIONS


def get_cloud_region(
    cloud: Cloud,
    region_id: str,
    gcp_project: Optional[str] = None,
):
    regions = get_regions(gcp_project)
    matches = [r for r in regions if r.cloud == cloud and r.region_id == region_id]
    if not matches:
        print(f"{cloud}")
        raise ValueError(f"Cannot find region {cloud}{region_id}")
    else:
        assert len(matches) == 1, matches
        ret = matches[0]
        return ret


def interregion_distance(r1: CloudRegion, r2: CloudRegion):
    assert not [
        x for x in [r1.lat, r1.long, r2.lat, r2.long] if x is None
    ], f"All regions should have coords {r1}, {r2}"
    ret = geopy.distance.distance((r1.lat, r1.long), (r2.lat, r2.long)).km
    assert (r1 == r2) == (ret == 0), "Expect 0 km if and only if same region"
    return ret


if __name__ == "__main__":
    pairs = itertools.product(get_regions(), get_regions())
    for pair in pairs:
        print(pair, interregion_distance(pair[0], pair[1]), "km")
