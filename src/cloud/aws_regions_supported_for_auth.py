import json
import logging
import os

from cloud.clouds import CloudRegion, Cloud
from util.subprocesses import run_subprocess

__SUPPORTED_AUTH_AWS_REGIONS_CACHE = {}
__AWS_REGIONS_SUPPORT_CACHE_FILE = "reference_data/supported_aws_auth_regions.json"


def __supported_auth_aws_regions_cache():
    global __SUPPORTED_AUTH_AWS_REGIONS_CACHE
    if (
        __SUPPORTED_AUTH_AWS_REGIONS_CACHE
    ):  # We will alwaysload empty file until we have some values, then we'll have a cache
        return __SUPPORTED_AUTH_AWS_REGIONS_CACHE

    try:
        with open(__AWS_REGIONS_SUPPORT_CACHE_FILE) as f:
            __SUPPORTED_AUTH_AWS_REGIONS_CACHE = json.load(f)
            logging.info(
                "Loaded supported AWS Regions as %s",
                __SUPPORTED_AUTH_AWS_REGIONS_CACHE,
            )

    except FileNotFoundError:
        __SUPPORTED_AUTH_AWS_REGIONS_CACHE = {}

    return __SUPPORTED_AUTH_AWS_REGIONS_CACHE


def __add_to_supported_aws_regions_cache(r: str, is_supported: bool):
    global __SUPPORTED_AUTH_AWS_REGIONS_CACHE
    __SUPPORTED_AUTH_AWS_REGIONS_CACHE[r] = is_supported
    __SUPPORTED_AUTH_AWS_REGIONS_CACHE = dict(
        sorted(__SUPPORTED_AUTH_AWS_REGIONS_CACHE.items(), key=lambda i: (i[1], i[0]))
    )
    with open(__AWS_REGIONS_SUPPORT_CACHE_FILE, "w") as f:
        logging.info("Adding %s, AWS supported region: %s", r, is_supported)

        json.dump(__SUPPORTED_AUTH_AWS_REGIONS_CACHE, f, indent=2)


def is_unsupported_auth_aws_region(r: CloudRegion):
    if r.cloud != Cloud.AWS:
        return False

    cached_value = __supported_auth_aws_regions_cache().get(r.region_id, None)
    if cached_value is not None:
        return not cached_value

    try:
        run_subprocess(
            "./scripts/aws-test-auth.sh",
            env={"PATH": os.environ.get("PATH"), "REGION": r.region_id},
        )
    except ChildProcessError as cpe:
        is_supported = False
    else:
        is_supported = True
    logging.info(
        "Discovered %s is a %s AWS region",
        r.region_id,
        "supported" if is_supported else "unsupported",
    )
    __add_to_supported_aws_regions_cache(r.region_id, is_supported)
    return not is_supported

