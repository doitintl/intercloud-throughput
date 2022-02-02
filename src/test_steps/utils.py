import os
from typing import List, Tuple

from cloud.clouds import CloudRegion


def env_for_singlecloud_subprocess(run_id, cloud_region):
    return {
        "PATH": os.environ["PATH"],
        "REGION": cloud_region.region_id,
        "RUN_ID": run_id,
    } | cloud_region.env()


def unique_regions(
    region_pairs: List[Tuple[CloudRegion, CloudRegion]]
) -> List[CloudRegion]:
    ret = []
    for p in region_pairs:
        for i in [0, 1]:
            if p[i] not in ret:
                ret.append(p[i])
    return ret
