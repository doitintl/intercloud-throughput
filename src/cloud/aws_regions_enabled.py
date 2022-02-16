import json
import logging
import os

from cloud.clouds import Region, Cloud
from util.subprocesses import run_subprocess

__cache_ = {}
__cache_file = "region_data/enabled_aws_regions_cache.json"


def __cache():
    global __cache_
    if (
        __cache_
    ):  # We will alwaysload empty file until we have some values, then we'll have a cache
        return __cache_

    try:
        with open(__cache_file) as f:
            d = json.load(f)
            # Remove comments
            d = {k: v for k, v in d.items() if not k.startswith("__")}
            __cache_ = d
            logging.info(
                "Supported AWS Regions as %s",
                __cache_,
            )

    except FileNotFoundError:
        __cache_ = {}

    return __cache_


def __add_to_cache(r: str, is_supported: bool):
    global __cache_
    __cache_[r] = is_supported
    __cache_ = dict(sorted(__cache_.items(), key=lambda i: (i[1], i[0])))
    with open(__cache_file, "w") as f:
        logging.info("Adding %s, AWS supported region: %s", r, is_supported)
        json.dump(__cache_, f, indent=2)


def is_nonenabled_auth_aws_region(r: Region):
    if r.cloud != Cloud.AWS:
        return False

    cached_value = __cache().get(r.region_id, None)
    if cached_value is not None:
        return not cached_value

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
