from __future__ import annotations

import csv
import inspect
import itertools
import logging
import re
from enum import Enum
from functools import total_ordering
from typing import Dict
from typing import List, Optional

import geopy.distance

from util.utils import gcp_default_project, set_cwd

basename_key_for_aws_ssh = "cloud-perf"


class Cloud(Enum):
    GCP = "GCP"
    AWS = "AWS"

    def __str__(self):
        return self.name


@total_ordering
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
        assert isinstance(cloud, Cloud), type(cloud)
        assert re.match(r"[a-z][a-z-]+\d$", region_id)
        assert (cloud == Cloud.GCP) == bool(gcp_project), f"{cloud} and {gcp_project}"

        self.lat = lat
        self.long = long
        self.cloud = cloud
        self.region_id = region_id
        self.gcp_project = gcp_project

    def script(self):
        return f"./scripts/{self.lowercase_cloud_name()}-launch.sh"

    def deletion_script(self):
        return f"./scripts/{self.lowercase_cloud_name()}-delete-instances.sh"

    def script_for_test_from_region(self):
        return f"./scripts/do-one-test-from-{self.lowercase_cloud_name()}.sh"

    def __repr__(self):
        gcp = "=" + self.gcp_project if self.gcp_project else ""
        return f"{self.cloud.name}-{self.region_id}{gcp}"

    def __hash__(self):
        return hash(repr(self))

    def env(self) -> Dict[str, str]:
        envs = {
            Cloud.GCP: {"PROJECT_ID": self.gcp_project},
            Cloud.AWS: {"BASE_KEYNAME": basename_key_for_aws_ssh},
        }
        return envs[self.cloud]

    def lowercase_cloud_name(self):
        return self.cloud.name.lower()

    def __lt__(self, other):
        """Note @total_ordering above"""
        return repr(self) < repr(other)

    def __eq__(self, other):
        return (
            self.region_id == other.region_id
            and self.cloud == other.cloud
            and self.gcp_project == other.gcp_project
        )


__REGIONS: List[CloudRegion]
__REGIONS = []


def get_regions(gcp_project: Optional[str] = None) -> List[CloudRegion]:
    """ "
    :param gcp_project is optional, if provided, will be used for GCP regions. Otherwise, built-in default will be used.
    """
    # Though each CloudRegion can take a gcp_project parameter,
    # for now we only support 1 gcp project for all.
    # So, only_gcp_project only exists to impose that constraint
    only_gcp_project = None

    def gcp_proj(cld, gcp_project):
        if cld == Cloud.GCP.name:
            ret = gcp_project or gcp_default_project()
            nonlocal only_gcp_project
            assert (
                not only_gcp_project or ret == only_gcp_project
            ), f"{ret}!={only_gcp_project}"
            only_gcp_project = only_gcp_project or ret  # could omit only_gcp_project or
            return ret
        else:
            return

    global __REGIONS

    if not __REGIONS:

        fp = open(f"./reference_data/locations.csv")
        rdr = csv.DictReader(filter(lambda row_: row_[0] != "#", fp))
        for row in rdr:

            lat_s = row["latitude"]
            long_s = row["longitude"]
            if lat_s is not None and long_s is not None:
                lat = float(lat_s)
                long = float(long_s)
            else:
                lat = long = None

            cloud_s = row["cloud"]

            __REGIONS.append(
                CloudRegion(
                    Cloud(cloud_s),
                    row["region"],
                    lat,
                    long,
                    gcp_proj(cloud_s, gcp_project),
                )
            )
        fp.close()
    return __REGIONS


def get_region(
    cloud: [Cloud | str],
    region_id: str,
    gcp_project: Optional[str] = None,
):
    regions = get_regions(gcp_project)
    if isinstance(cloud, str):
        cloud = Cloud(cloud)
    assert isinstance(cloud, Cloud), cloud
    matches = [r for r in regions if r.cloud == cloud and r.region_id == region_id]
    if not matches:
        print(f"{cloud}")
        raise ValueError(f"Cannot find region {cloud}{region_id}")
    else:
        assert len(matches) == 1, matches
        ret = matches[0]
        return ret


def interregion_distance(r1: CloudRegion, r2: CloudRegion):

    ret = geopy.distance.distance((r1.lat, r1.long), (r2.lat, r2.long)).km
    assert (r1 == r2) == (ret == 0), "Expect 0 km if and only if same region"
    return ret


def print_interregion_distances():
    pairs = itertools.product(get_regions(), get_regions())
    for pair in pairs:
        logging.info("%s: %s km", pair, interregion_distance(pair[0], pair[1]))


if __name__ == "__main__":
    set_cwd()
    print_interregion_distances()
