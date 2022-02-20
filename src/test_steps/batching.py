import argparse
import collections
import itertools
import logging
import math
from itertools import product
from typing import Union, Callable, Optional

from cloud.aws_regions_enabled import is_nonenabled_auth_aws_region
from cloud.clouds import (
    Cloud,
    Region,
    get_regions,
    interregion_distance,
    get_region,
)
from history.attempted import (
    without_already_succeeded,
    write_attempted_tests,
    already_succeeded,
)
from history.results import load_history
from test_steps.create_vms import create_vms
from test_steps.delete_vms import delete_vms
from test_steps.do_test import do_batch
from test_steps.utils import unique_regions
from util.utils import chunks, parse_infinity

default_batch_size = math.inf
default_max_batches = 1
default_min_distance = 0
default_max_distance = math.inf
default_machine_types = "AWS,t3.nano;GCP,e2-small"


def batch_setup_test_teardown(
    run_id, region_pairs: list[tuple[Region, Region]], machine_types: dict[Cloud, str]
):
    logging.info("Tests in batch: %s", region_pairs)
    write_attempted_tests(run_id, region_pairs, machine_types)
    # VMs will still be cleaned up if launch or tests fail
    vm_region_and_address_infos = create_vms(region_pairs, run_id, machine_types)
    do_batch(run_id, vm_region_and_address_infos)
    delete_vms(run_id, unique_regions(region_pairs))


def all_tests_done(
    regions: list[Region], cloudpairs: Optional[list[tuple[Cloud, Cloud]]]
):
    pairs = filter_crossproduct_regions_by_cloudpair(regions, cloudpairs)
    succeeded_pairs = already_succeeded()
    return all(p in succeeded_pairs for p in pairs)


def __arrange_in_testbatches(
    regions_per_batch: Union[int, float],
    max_batches: Union[int, float],
    cloudpairs: list[tuple[Cloud, Cloud]],
    preselected_region_pairs: list[tuple[Region, Region]],
    min_distance: Union[int, float],
    max_distance: Union[int, float],
) -> list[list[tuple[Region, Region]]]:
    if regions_per_batch < 2:
        raise ValueError(
            "Each batch of regions must have 2 or more regions for a meaningful test"
        )
    if preselected_region_pairs:
        batches_of_tests = [preselected_region_pairs]
    else:
        regions = get_regions()

        regions = [r for r in regions if not is_nonenabled_auth_aws_region(r)]
        regions = __sort_regions(regions, bool(cloudpairs))
        if all_tests_done(regions, cloudpairs):
            logging.info("Did all possible tests")
            return []
        batches_of_regions = list(chunks(regions, regions_per_batch))

        batches_of_tests: list[list[tuple[Region, Region]]]

        while True:

            if max_batches < math.inf:
                batches_of_regions_trunc = batches_of_regions[:max_batches]
            else:
                batches_of_regions_trunc = batches_of_regions
            batches_of_tests: list[list[tuple[Region, Region]]]
            batches_of_tests = __make_test_batches(
                batches_of_regions_trunc, cloudpairs, min_distance, max_distance
            )

            # If no tests are built this way, because all possibilities in these regions have been done,
            # We increase max_batches and try again
            if batches_of_tests:
                break
            elif max_batches >= len(batches_of_regions):
                logging.info("Could not find tests that have not yet been run; exiting")
                break
            else:
                logging.info(
                    "Made no batches; max was %d. Will retry with bigger max_batches",
                    max_batches,
                )
                max_batches += 1
                continue

    logging.info(
        f"%d tests in %d batches%s",
        sum(len(b1) for b1 in batches_of_tests),
        len(batches_of_tests),
        ""
        if len(batches_of_tests) < 2
        else " of sizes " + ", ".join(str(len(b)) for b in batches_of_tests),
    )
    return batches_of_tests


def __ascending_freq_keyfunc() -> Callable[[Region], int]:
    """:return a function that will allow sorting in ascending order of freq of appearance
    of a CloudRegion in post runs"""
    results: list[dict] = load_history()
    regions_from_results_src = [
        (get_region(d["from_cloud"], d["from_region"])) for d in results
    ]
    regions_from_results_dst = [
        (get_region(d["to_cloud"], d["to_region"])) for d in results
    ]

    regions_from_results = collections.Counter(
        regions_from_results_src + regions_from_results_dst
    )

    counts = collections.Counter(regions_from_results)

    def key_func(region: Region) -> int:
        return counts[region]

    return key_func


def __sort_regions(regions: list[Region], interleave: bool):
    by_clouds = []
    # First sort puts regions in order of Cloud first (AWS, GCP),
    # then in order of region, e.g., us, sa, northamerican eu, au, asia, af,
    # which *very* roughly is in order of general popularity.
    regions.sort(reverse=True)
    # Next sort puts regions in order of how much they were neglectied in previous test runs
    # Sorting is table, so where no data is available here,  the previous sort will hold

    for c in Cloud:
        cloud_regions = [r for r in regions if r.cloud == c]
        by_clouds.append(cloud_regions)

    zipped = itertools.zip_longest(*by_clouds)
    regions = itertools.chain.from_iterable(zipped)
    regions = [r for r in regions if r]

    if not interleave:
        regions.sort(key=__ascending_freq_keyfunc())

    return regions


def __make_test_batches(
    batches_of_regions: list[list[Region]],
    cloudpairs: list[tuple[Cloud, Cloud]],
    min_distance: Union[int, float],
    max_distance: Union[int, float],
):
    batches_of_tests = []
    for batch in batches_of_regions:

        region_pairs = filter_crossproduct_regions_by_cloudpair(batch, cloudpairs)

        len_before_remove_succeeded = len(region_pairs)
        region_pairs = without_already_succeeded(region_pairs)
        if len(region_pairs) != len_before_remove_succeeded:
            logging.info(
                "Dropping %d region pairs that already succeeded, leaving %d",
                len_before_remove_succeeded - len(region_pairs),
                len(region_pairs),
            )

        len_before_dist_filter = len(region_pairs)
        region_pairs = [
            p
            for p in region_pairs
            if min_distance <= interregion_distance(p[0], p[1]) <= max_distance
        ]
        if len(region_pairs) != len_before_dist_filter:
            logging.info(
                "Dropping %s region pairs that were outside the specified distance limits [%s,%s], leaving %s",
                # Use %s not $d because could be inf
                len_before_dist_filter - len(region_pairs),
                min_distance,
                max_distance,
                len(region_pairs),
            )
        if region_pairs:  # Might have not valid tests at this point
            batches_of_tests.append(region_pairs)
    return batches_of_tests


def filter_crossproduct_regions_by_cloudpair(
    regions: list[Region], cloudpairs: Optional[list[tuple[Cloud, Cloud]]]
):
    region_pairs = list(filter(lambda p: p[0] != p[1], product(regions, regions)))

    if cloudpairs:  # filter to match only those that have thse cloudpairs
        region_pairs = [
            region_pair
            for region_pair in region_pairs
            if (region_pair[0].cloud, region_pair[1].cloud) in cloudpairs
        ]

    return region_pairs


def __parse_region_pairs(
    region_pairs: str,
) -> Optional[list[tuple[Region, Region]]]:
    if not region_pairs:
        return None

    def parse_region(s: str) -> Region:
        cloud_and_region = s.split(".")
        if len(cloud_and_region) != 2:
            raise ValueError(f"{s} is not a dot-separated cloud-region string")
        return get_region(*cloud_and_region)

    pairs_s: list[str] = region_pairs.split(";")
    pairs_s = [t for t in pairs_s if t]
    test_pairs: list[list[str]] = [p.split(",") for p in pairs_s]
    badly_formed = [p for p in test_pairs if len(p) != 2]
    if badly_formed:
        raise ValueError(
            f"Not comma-separated cloud-region pairs, each pair semi-colon-separated; "
            f"Correct format is AWS.us-east-1,GCP.us-central1;GCP.US-central1,AWS.us-east-1\n"
            f"Incorrect value was {region_pairs}"
        )
    pairs_regions = [(parse_region(p[0]), parse_region(p[1])) for p in test_pairs]
    return pairs_regions


def __command_line_args():
    parser = argparse.ArgumentParser(description="", allow_abbrev=True)
    parser.add_argument(
        "--region_pairs",
        type=str,
        default=None,
        help="Specific tests to run, where cloud and region names are separated by dot; "
        "source and destination are separated by comma; "
        "and pairs are separated by semicolon, "
        "as for example: AWS.us-east-1,AWS.us-east-2;AWS.us-west-1,GCP.us-west3. "
        "\nIf this is used, the other flags are ignored. "
        '\nNote that all these specified tests are run simultaneously -- as one "batch" in the terminology of the other flags). '
        "\nIf you want to run multiple batches of specified tests that you specify, run this tool multiple times.",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=default_batch_size,
        help="Limits the  number of regions to be tested simultaneously (i.e.,in each batch). "
        "\nEach cross-product combination will be tested with both directions of source/destination "
        "(but without intra-region (self-to-self) pairs). "
        "\nThus, there will be (batch_size * (batch_size-1))  tests in total."
        f'\nDefault is "{default_batch_size}"'
        "\nIf batch_size=inf, there will be 2070 tests across 46 regions (assuming default enablement of AWS regions). "
        "This is the fastest and most efficient, but means running 46 (very cheap) instances (for under 10 minutes). "
        "\nThe parameter is ignored if --region_pairs is used.",
    )

    parser.add_argument(
        "--max_batches",
        type=int,
        default=default_max_batches,
        help="Limits the number of batches of regions. "
        "\nTogether with batch_size, this can be used to limit number of tests. "
        f"\nDefault is {default_max_batches}."
        "\nThe parameter is ignored if --region_pairs is used.",
    )

    parser.add_argument(
        "--clouds",
        type=str,
        default="",
        help="Limits selection of tests to these directed cloud pairs."
        "\nComma-separated cloud pairs; multiple such pairs can be separated by semicolons."
        '\nFor example "GCP,AWS;AWS,GCP" means do only tests that are from GCP to AWS or AWS to GCP.'
        "\nThe parameter is ignored if --region_pairs is used.",
    )
    parser.add_argument(
        "--min_distance",
        type=int,
        default=default_min_distance,
        help="\nMinimum distance in km between source and destination for a test."
        "\nThe parameter is ignored if --region_pairs is used.",
    )
    parser.add_argument(
        "--max_distance",
        type=int,
        default=default_max_distance,
        help="\nMaximum distance in km between source and destination for a test."
        "\nThe parameter is ignored if --region_pairs is used.",
    )

    parser.add_argument(
        "--machine_types",
        type=str,
        default=default_machine_types,
        help='\nMachine types to use for each cloud in the format "AWS,t3-nano,GCP,e2-micro".'
        "\nYou can specify any and all clouds here. Where unspecified, the default for that cloud is used.",
    )

    args = parser.parse_args()

    if bool(args.region_pairs) and bool(
        args.max_batches != default_max_batches
        or args.batch_size != default_batch_size
        or args.min_distance != default_min_distance
        or args.max_distance != default_max_distance
        or args.clouds
    ):
        raise ValueError(
            "Cannot specify both --region_pairs and other params: %s", args
        )
    return args


def __parse_machine_types(machine_types) -> dict[Cloud, str]:
    per_cloud = machine_types.split(";")
    assert all(p.count(",") == 1 for p in per_cloud), (
        f"For machine_types, expect semicolon-separated pairs of "
        f'comma-separated Cloud,machine-type, was "%s" machine_types'
    )
    splits = [p.split(",") for p in per_cloud]
    return {Cloud(s[0]): s[1] for s in splits}


def __machine_types_per_cloud(args) -> dict[Cloud, str]:
    machine_types_dflt = __parse_machine_types(default_machine_types)
    machine_types_from_args = __parse_machine_types(args.machine_types)
    machine_types = machine_types_dflt | machine_types_from_args
    return machine_types


def setup_batches() -> tuple[list[list[tuple[Region, Region]]], dict[Cloud, str]]:
    args = __command_line_args()
    if args.clouds:
        clouds = [
            (Cloud(p[0]), Cloud(p[1]))
            for p in [cloudpair_s.split(",") for cloudpair_s in args.clouds.split(";")]
        ]
    else:
        clouds = []

    batches = __arrange_in_testbatches(
        parse_infinity(args.batch_size),
        parse_infinity(args.max_batches),
        clouds,
        __parse_region_pairs(args.region_pairs),
        args.min_distance,
        args.max_distance,
    )

    if not batches:
        logging.info("No tests to run that did not already succeeed")
        exit(0)

    return batches, __machine_types_per_cloud(args)
