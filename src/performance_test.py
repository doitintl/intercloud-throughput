#!/usr/bin/env python
import argparse
import collections
import itertools
import logging
import math
from itertools import product
from typing import Optional, Callable, Union

from cloud.aws_regions_enabled import is_nonenabled_auth_aws_region
from cloud.clouds import (
    Cloud,
    CloudRegion,
    get_regions,
    get_region,
)
from graph.plot_chart import graph_full_testing_history
from history.attempted import (
    without_already_succeeded,
    write_attempted_tests,
)
from history.results import load_past_results
from test_steps.create_vms import create_vms
from test_steps.delete_vms import delete_vms
from test_steps.do_test import do_tests
from test_steps.utils import unique_regions
from util.utils import set_cwd, random_id, chunks, Timer, date_s, parse_infinity

default_batch_sz = math.inf
default_max_batches = math.inf
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def __setup_and_tests_and_teardown(
    run_id: str, region_pairs: list[tuple[CloudRegion, CloudRegion]]
):
    # VMs will still be cleaned up if launch or tests fail

    vm_region_and_address_infos = create_vms(region_pairs, run_id)
    logging.info(vm_region_and_address_infos)
    do_tests(run_id, vm_region_and_address_infos)
    delete_vms(run_id, unique_regions(region_pairs))


def test_batch(region_pairs: list[tuple[CloudRegion, CloudRegion]], run_id):
    write_attempted_tests(region_pairs)
    logging.info("Will test %s", region_pairs)

    __setup_and_tests_and_teardown(run_id, region_pairs)


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


def __batches_of_tests(
    regions_per_batch: Union[int, float],  # float only for inf
    max_batches: Union[int, float],  # float only for inf
    cloud: Cloud,
    cloudpairs: list[tuple[Cloud, Cloud]],
    preselected_region_pairs: list[tuple[CloudRegion, CloudRegion]],
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
            batches_of_tests = __make_test_batches(batches_of_regions_trunc, cloudpairs)

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
    batches_of_regions: list[list[CloudRegion]], cloudpairs: list[tuple[Cloud, Cloud]]
):
    batches_of_tests = []
    for b in batches_of_regions:
        crossproduct_regionpairs = list(filter(lambda p: p[0] != p[1], product(b, b)))
        len_all = len(crossproduct_regionpairs)
        if cloudpairs:
            crossproduct_regionpairs = [
                region_pair
                for region_pair in crossproduct_regionpairs
                if (region_pair[0].cloud, region_pair[1].cloud) in cloudpairs
            ]
        if len(crossproduct_regionpairs) != len_all:
            logging.info(
                "From batch, dropping %d region pairs that were not in the specified list of cloud pairs, leaving %d",
                len_all - len(crossproduct_regionpairs),
                len(crossproduct_regionpairs),
            )

        len_before = len(crossproduct_regionpairs)
        crossproduct_regionpairs = without_already_succeeded(crossproduct_regionpairs)
        if len(crossproduct_regionpairs) != len_before:
            logging.info(
                "Dropping %d region pairs that already succeeded, leaving %d",
                len_before - len(crossproduct_regionpairs),
                len(crossproduct_regionpairs),
            )
        if crossproduct_regionpairs:  # Might have already done all these tests
            batches_of_tests.append(crossproduct_regionpairs)
    return batches_of_tests


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
        type=str,
        default=default_batch_sz,
        help="Number of regions to be tested simultaneously. "
        "\nEach cross-product combination will be tested with both directions of source/destination "
        "(but without intra-region (self-to-self) pairs). "
        "\nThus, there will be (batch_size * (batch_size-1))  tests in a batch)"
        '\nDefault is "inf"'
        "\nIf batch_size=inf, there will be 2070 tests across 46 regions (assuming default enablement of AWS regions). "
        "This is the fastest and most efficient, but means running 46 (very cheap) instances (for under 10 minutes). "
        "\nThe parameter is ignored if --region_pairs is used.",
    )

    parser.add_argument(
        "--max_batches",
        type=int,
        default=default_max_batches,
        help="Max number of batches of regions. "
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
        help="\nDirected cloud pairs to select."
        "\nComma-separated cloud pairs; multiple such pairs can be separated by semicolons."
        '\nFor example "GCP,AWS;AWS,GCP" means do only tests that are from GCP to AWS or AWS to GCP'
        "\nCannot be used with --cloud."
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
            or args.cloud
            or args.clouds
        )
    ):
        raise ValueError(
            "Cannot specify both --region_pairs and other params: %s", args
        )
    return args


def main():
    logging.info("Started at %s", date_s())
    args = __command_line_args()

    if args.clouds:
        clouds = [
            (Cloud(p[0]), Cloud(p[1]))
            for p in [cloudpair_s.split(",") for cloudpair_s in args.clouds.split(";")]
        ]
    else:
        clouds = []

    batches = __batches_of_tests(
        parse_infinity(args.batch_size),
        parse_infinity(args.max_batches),
        args.cloud,
        clouds,
        __parse_region_pairs(args.region_pairs),
    )
    if not batches:
        logging.info("No tests to run that did not already succeeed")
        exit(0)

    run_id = random_id()
    logging.info("Run ID is %s", run_id)

    for batch in batches:
        test_batch(batch, run_id)

    graph_full_testing_history()


if __name__ == "__main__":
    with Timer("Full run"):
        set_cwd()
        main()
