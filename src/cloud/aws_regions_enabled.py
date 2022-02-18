import json
import logging
import os

from cloud.clouds import Region, Cloud
from util.subprocesses import run_subprocess

__enabled_regions = {}

__enabled_regions_file = "region_data/enabled_aws_regions.json"

def __get_enabled_regions():
    global __enabled_regions
    if (
        __enabled_regions
    ):  # We will always load empty file until we have some values, then we'll have a cache
        return __enabled_regions

    try:
        with open(__enabled_regions_file) as f:
            d = json.load(f)
            # Remove comments
            d = {k: v for k, v in d.items() if not k.startswith("__")}
            __enabled_regions = d
            logging.info(
                "Supported AWS Regions as %s",
                __enabled_regions,
            )

    except FileNotFoundError:
        __enabled_regions = {}

    return __enabled_regions


def __add_to_cache(region: str, is_supported: bool):
    global __enabled_regions
    __enabled_regions[region] = is_supported
    #Sort by region and cloud (which is only AWS here)
    __enabled_regions = dict(sorted(__enabled_regions.items(), key=lambda i: (i[1], i[0])))
    with open(__enabled_regions_file, "w") as f:
        logging.info("Adding %s, AWS supported region: %s", region, is_supported)
        json.dump(__enabled_regions, f, indent=2)


def is_nonenabled_auth_aws_region(r: Region):
    if r.cloud != Cloud.AWS:
        return False

    stored_value = __get_enabled_regions().get(r.region_id, None)
    if stored_value is not None:
        return not stored_value

    try:
        run_subprocess(
            "./scripts/aws-test-auth.sh",
            env={"PATH": os.environ.get("PATH"), "REGION": r.region_id},
        )
    except ChildProcessError:
        is_enabled = False
    else:
        is_enabled = True
    logging.info(
        "Discovered %s is %s enabled",
        r.region_id,
        "" if is_enabled else "not ",
    )
    __add_to_cache(r.region_id, is_enabled)
    return not is_enabled
