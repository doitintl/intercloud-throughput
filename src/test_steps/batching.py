import argparse
import collections
import itertools
import logging
import math
from itertools import product
from typing import Union, Callable, Optional

from cloud.aws_regions_enabled import is_nonenabled_auth_aws_region
from cloud.clouds import Cloud, CloudRegion, get_regions, interregion_distance, get_region
from history.attempted import without_already_succeeded, write_attempted_tests
from history.results import load_past_results
from test_steps.create_vms import create_vms
from test_steps.delete_vms import delete_vms
from test_steps.do_test import do_tests
from test_steps.utils import unique_regions

from util.utils import chunks, parse_infinity


default_batch_sz = math.inf
default_max_batches = math.inf
default_min_distance = 0
default_max_distance = math.inf

def batch_setup_test_teardown(region_pairs: list[tuple[CloudRegion, CloudRegion]], run_id):
    write_attempted_tests(region_pairs)
    logging.info("Will test %s", region_pairs)

    # VMs will still be cleaned up if launch or tests fail
    vm_region_and_address_infos = create_vms(region_pairs, run_id)
    logging.info(vm_region_and_address_infos)
    do_tests(run_id, vm_region_and_address_infos)
    delete_vms(run_id, unique_regions(region_pairs))

def __arrange_in_testbatches(
    regions_per_batch: Union[int, float],
    max_batches: Union[int, float],
    cloud: Cloud,
    cloudpairs: list[tuple[Cloud, Cloud]],
    preselected_region_pairs: list[tuple[CloudRegion, CloudRegion]],
    min_distance: Union[int, float],
    max_distance: Union[int, float],
) -> list[list[tuple[CloudRegion, CloudRegion]]]:

    if regions_per_batch < 2:
        raise ValueError(
            "Each batch of regions must have 2 or more regions for a meaningful test"
        )
    if preselected_region_pairs:
        batches_of_tests = [preselected_region_pairs]
    else:
        regions = get_regions()

        if cloud:
            regions = [r for r in regions if cloud == r.cloud]

        regions = [r for r in regions if not is_nonenabled_auth_aws_region(r)]
        regions = __sort_regions(regions, bool(cloudpairs))
        batches_of_regions = list(chunks(regions, regions_per_batch))

        batches_of_tests: list[list[tuple[CloudRegion, CloudRegion]]]
        while True:
            if max_batches < math.inf:
                batches_of_regions_trunc = batches_of_regions[:max_batches]
            else:
                batches_of_regions_trunc = batches_of_regions
            batches_of_tests: list[list[tuple[CloudRegion, CloudRegion]]]
            batches_of_tests = __make_test_batches(
                batches_of_regions_trunc, cloudpairs, min_distance, max_distance
            )

            # If no tests are built this way, because all possibilities in these regions have been done,
            # We increase max_batches and try again
            if not batches_of_tests and not __max_possible(
                max_batches, len(get_regions()), regions_per_batch
            ):
                logging.info(
                    "Made no batches; max was %d. Will retry with bigger max_batches",
                    max_batches,
                )
                max_batches += 1
                continue
            else:
                break

    logging.info(
        f"Will run %d tests in %d batches%s",
        sum(len(b1) for b1 in batches_of_tests),
        len(batches_of_tests),
        ""
        if len(batches_of_tests) < 2
        else " of sizes " + ", ".join(str(len(b)) for b in batches_of_tests),
    )
    return batches_of_tests

def __ascending_freq_keyfunc() -> Callable[[CloudRegion], int]:
    """:return a function that will allow sorting in ascending order of freq of appearance
    of a CloudRegion in post runs"""
    results: list[dict] = load_past_results()
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

    def key_func(region: CloudRegion) -> int:
        return counts[region]

    return key_func



def __sort_regions(regions: list[CloudRegion], interleave: bool):
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


def __max_possible(max_batches, num_regions, regions_per_batch):
    """Return True if max_batches is so large that there would be no benefit in increasing it, because
    The maximum number of directed interregion pairs is less than the number of tests that could be generated
    given this max_batches and regions_per_batch"""
    max_tests_that_could_be_allowed = (
        max_batches * regions_per_batch * (regions_per_batch - 1)
    )
    max_tests_possible_for_num_regions = num_regions * (num_regions - 1)
    return max_tests_that_could_be_allowed > max_tests_possible_for_num_regions


def __make_test_batches(
    batches_of_regions: list[list[CloudRegion]],
    cloudpairs: list[tuple[Cloud, Cloud]],
    min_distance: Union[int, float],
    max_distance: Union[int, float],
):

    batches_of_tests = []
    for b in batches_of_regions:
        region_pairs = list(filter(lambda p: p[0] != p[1], product(b, b)))
        len_all = len(region_pairs)
        if cloudpairs:
            region_pairs = [
                region_pair
                for region_pair in region_pairs
                if (region_pair[0].cloud, region_pair[1].cloud) in cloudpairs
            ]
        if len(region_pairs) != len_all:
            logging.info(
                "From batch, dropping %d region pairs that were not in the specified list of cloud pairs, leaving %d",
                len_all - len(region_pairs),
                len(region_pairs),
            )

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
                "Dropping %d region pairs that were outside the specified distance limits [%d,%d], leaving %d",
                len_before_dist_filter - len(region_pairs),
                min_distance,
                max_distance,
                len(region_pairs)
            )
        if region_pairs:  # Might have not valid tests at this point
            batches_of_tests.append(region_pairs)
    return batches_of_tests


def __parse_region_pairs(
    region_pairs: str,
) -> Optional[list[tuple[CloudRegion, CloudRegion]]]:
    if not region_pairs:
        return None

    def parse_region(s: str) -> CloudRegion:
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
            f"{pairs_s} is not comma-separated cloud-region pairs, each pair semi-colon-separated: See {badly_formed}"
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
        '\nNote that  all these specified tests are run simultaneously -- as one "batch" in the terminology of the other flags). '
        "\nIf you want to run multiple batches of specified tests that you specify, run this tool multiple times.",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=default_batch_sz,
        help="Limits the  number of regions to be tested simultaneously (i.e.,in each batch). "
        "\nEach cross-product combination will be tested with both directions of source/destination "
        "(but without intra-region (self-to-self) pairs). "
        "\nThus, there will be (batch_size * (batch_size-1))  tests in total."
        '\nDefault is "inf"'
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
        '\nDefault is "inf" and indicates "do all", no maximum number of batches. '
        "\nThe parameter is ignored if --region_pairs is used.",
    )

    parser.add_argument(
        "--cloud",
        type=Cloud,
        default=None,
        help='"GCP" or "AWS" means ignore tests that use a different cloud. '
        '\nDefault means "Don\'t ignore any clouds."'
        "\nCannot be used with --cloud."
        "\nThe parameter is ignored if --region_pairs is used.",
    )
    parser.add_argument(
        "--clouds",
        type=str,
        default="",
        help="Limits selection of tests to these directed cloud pairs."
        "\nComma-separated cloud pairs; multiple such pairs can be separated by semicolons."
        '\nFor example "GCP,AWS;AWS,GCP" means do only tests that are from GCP to AWS or AWS to GCP'
        "\nCannot be used with --cloud."
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

    args = parser.parse_args()

    if args.cloud and args.clouds:
        raise ValueError("Cannot specify both --cloud and --clouds")

    if (
        True
        == bool(args.region_pairs)
        == bool(
            args.max_batches != default_max_batches
            or args.batch_size != default_batch_sz
            or args.min_distance != default_min_distance
            or args.max_distance != default_max_distance
            or args.cloud
            or args.clouds
        )
    ):
        raise ValueError(
            "Cannot specify both --region_pairs and other params: %s", args
        )
    return args


def setup_batches():
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
        args.cloud,
        clouds,
        __parse_region_pairs(args.region_pairs),
        args.min_distance,
        args.max_distance,
    )
    if not batches:
        logging.info("No tests to run that did not already succeeed")
        exit(0)
    return batches

