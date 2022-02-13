from __future__ import annotations

import csv
import re
from enum import Enum
from functools import total_ordering

import geopy.distance

from util.utils import gcp_default_project

basename_key_for_aws_ssh = "cloud-perf"


class Cloud(Enum):
    GCP = "GCP"
    AWS = "AWS"

    def __str__(self):
        return self.name


__PRIVATE__INIT__ = object()


@total_ordering
class Region:
    def __init__(
        self,
        private_init,
        cloud: Cloud,
        region_id: str,
        lat: float = None,
        long: float = None,
    ):
        if private_init is not __PRIVATE__INIT__:
            raise ValueError(
                'Call get_region() instead of  CloudRegion, which is kept "private" so that a cache can be built.'
            )

        assert isinstance(cloud, Cloud), type(cloud)
        assert re.match(r"[a-z][a-z-]+\d$", region_id)

        self.lat = lat
        self.long = long
        self.cloud = cloud
        self.region_id = region_id

    def script(self):
        return f"./scripts/{self.lowercase_cloud_name()}-launch.sh"

    def deletion_script(self):
        return f"./scripts/{self.lowercase_cloud_name()}-delete-instances.sh"

    def script_for_test_from_region(self):
        return f"./scripts/do-one-test-from-{self.lowercase_cloud_name()}.sh"

    def __repr__(self):
        return f"{self.cloud.name}.{self.region_id}"

    def __hash__(self):
        return hash(repr(self))

    def env(self) -> dict[str, str]:
        envs = {
            Cloud.GCP: {"PROJECT_ID": gcp_default_project()},
            Cloud.AWS: {"BASE_KEYNAME": basename_key_for_aws_ssh},
        }
        return envs[self.cloud]

    def lowercase_cloud_name(self):
        return self.cloud.name.lower()

    def __lt__(self, other):
        """Note @total_ordering above"""
        return repr(self) < repr(other)

    def __eq__(self, other):
        return self.region_id == other.region_id and self.cloud == other.cloud


__regions: list[Region]
__regions = []


def get_regions() -> list[Region]:
    global __regions

    if not __regions:

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

            region_id = row["region"]

            __regions.append(
                Region(__PRIVATE__INIT__, Cloud(cloud_s), region_id, lat, long)
            )
        fp.close()
    return __regions


def get_region(
    cloud: [Cloud | str],
    region_id: str,
) -> Region:
    regions = get_regions()
    if isinstance(cloud, str):
        cloud = Cloud(cloud)
    assert isinstance(cloud, Cloud), cloud
    matches = [r for r in regions if r.cloud == cloud and r.region_id == region_id]
    if not matches:
        print(f"{cloud}")
        raise ValueError(f"Cannot find region {cloud}.{region_id}")
    else:
        assert len(matches) == 1, matches
        ret = matches[0]
        return ret


def __samecity_crosscloud_datacenters() -> list[set[Region, Region]]:
    return [
        {get_region(*p[0]), get_region(*p[1])}
        for p in [
            ((Cloud.GCP, "europe-west3"), (Cloud.AWS, "eu-central-1")),
            ((Cloud.GCP, "asia-northeast1"), (Cloud.AWS, "ap-northeast-1")),
            ((Cloud.GCP, "asia-northeast2"), (Cloud.AWS, "ap-northeast-3")),
            ((Cloud.GCP, "asia-northeast3"), (Cloud.AWS, "ap-northeast-2")),
            ((Cloud.GCP, "asia-southeast1"), (Cloud.AWS, "ap-southeast-1")),
            ((Cloud.GCP, "australia-southeast1"), (Cloud.AWS, "ap-southeast-2")),
        ]
    ]


def interregion_distance(r1: Region, r2: Region):
    ret = geopy.distance.distance((r1.lat, r1.long), (r2.lat, r2.long)).km
    if ret == 0:
        if r1 == r2:
            pass  # Test within a single cloud's region. Use 0 though in fact a region can be spread out.
        else:
            if {r1, r2} in __samecity_crosscloud_datacenters():
                # Where we have identical coordinates for cross-cloud data-centers, it
                # means that a city's coordinates were used as an approximation.
                # We use 10 as an approximation for intra-city distance to avoid divide-by-zero errors.
                ret = 10
            else:
                assert False, (
                    f"Should not have zero distance for region "
                    f"pair unless these are known same-city data-centers {r1},{r2}"
                )

    return ret
