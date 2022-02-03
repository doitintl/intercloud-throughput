import argparse
import collections
import datetime
import itertools
import logging
import math
from itertools import product
from typing import List, Tuple, Optional, Dict, Callable

from cloud.aws_regions_enabled import is_non_enabled_auth_aws_region
from cloud.clouds import (
    Cloud,
    CloudRegion,
    get_regions,
    get_region,
)
from graph.graph import graph_full_testing_history
from history.attempted import (
    without_already_succeeded,
    write_attempted_tests,
)
from history.results import load_past_results
from test_steps.create_vms import create_vms
from test_steps.delete_vms import delete_vms
from test_steps.do_test import do_tests
from test_steps.utils import unique_regions
from util.utils import set_cwd, random_id, chunks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def __setup_and_tests_and_teardown(
    run_id: str, region_pairs: List[Tuple[CloudRegion, CloudRegion]]
):
    # Because we launch VMs and runs tests multithreaded, if one launch fails or one tests fails, running tests will not raise  an Exception.
    # So, VMs will still be cleaned up

    vm_region_and_address_infos = create_vms(region_pairs, run_id)
    logging.info(vm_region_and_address_infos)
    do_tests(run_id, vm_region_and_address_infos)
    delete_vms(run_id, unique_regions(region_pairs))


def test_batch(region_pairs: List[Tuple[CloudRegion, CloudRegion]], run_id):
    write_attempted_tests(region_pairs)
    logging.info("Will test %s", region_pairs)

    __setup_and_tests_and_teardown(run_id, region_pairs)


def __parse_region_pairs(
    region_pairs: str,
) -> Optional[List[Tuple[CloudRegion, CloudRegion]]]:
    if not region_pairs:
        return None

    def parse_region(s: str) -> CloudRegion:
        cloud_and_region = s.split(".")
        if len(cloud_and_region) != 2:
            raise ValueError(f"{s} is not a dot-separated cloud-region string")
        return get_region(*cloud_and_region)

    pairs_s: List[str] = region_pairs.split(";")
    test_pairs: List[List[str]] = [p.split(",") for p in pairs_s]
    if not all(len(pair) == 2 for pair in test_pairs):
        raise ValueError(f"{pairs_s} is not comma-separated cloud-region pairs, each pair semi-colon-separated")
    pairs_regions = [(parse_region(p[0]), parse_region(p[1])) for p in test_pairs]
    return pairs_regions


def __ascending_freq_keyfunc() -> Callable[[CloudRegion], Tuple[int, CloudRegion]]:
    """:return a function that will allow sorting in ascending order of freq of appearance
    of a CloudRegion in post runs, with the name of the CloudRegion as a tiebreaker"""
    results: List[Dict] = load_past_results()
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

    def key_func(region: CloudRegion) -> Tuple[int, CloudRegion]:
        return counts[region], region  # 'region' here is  tiebreaker

    return key_func


def __batches_of_tests(
    regions_per_batch: int,
    max_batches: int,
    one_cloud: Cloud,
    preselected_region_pairs: List[Tuple[CloudRegion, CloudRegion]],
) -> List[List[Tuple[CloudRegion, CloudRegion]]]:
    if preselected_region_pairs:
        batches_of_tests = [preselected_region_pairs]
    else:
        regions = get_regions()
        if regions_per_batch < 2:
            raise ValueError(
                "Each batch of regions must have 2 or more regions for a meaningful test"
            )

        if one_cloud:
            regions = [r for r in regions if one_cloud == r.cloud]

        regions = [r for r in regions if not is_non_enabled_auth_aws_region(r)]
        regions = __sort_regions(regions)
        batches_of_regions = list(chunks(regions, regions_per_batch))

        batches_of_tests: List[List[Tuple[CloudRegion, CloudRegion]]]
        while True:
            if max_batches < math.inf:
                batches_of_regions_trunc = batches_of_regions[:max_batches]
            else:
                batches_of_regions_trunc = batches_of_regions
            batches_of_tests: List[List[Tuple[CloudRegion, CloudRegion]]]
            batches_of_tests = __make_test_batches(batches_of_regions_trunc)

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
        __num_tests(batches_of_tests),
        len(batches_of_tests),
        ""
        if len(batches_of_tests) < 2
        else " of sizes " + ", ".join(str(len(b)) for b in batches_of_tests),
    )
    return batches_of_tests


def __sort_regions(regions):
    # 1. We sort by how many times we have already tested a region, so we can
    # spread our efforts across regions. See end of function.
    # 2. When there is not yet a history of testing,  we are starting our experiments based
    #     a. We interleave clouds just to get rich experiments.
    #     b. We order based on how roughly  how popular  regions are for use,
    #     starting with 'us', then 'eu','asia', 'af'. An alphabetical reversal accomplishes that.
    #     (Actually, 'sa'  comes before 'eu' this way,  but in general this ordering works.)

    # Sorting also sorts by Cloud
    # All GCP will come before all AWS, and regions sorted as mentioned above.
    regions.sort(reverse=True)
    # Interleave clouds
    by_clouds = [
        [r for r in regions if r.cloud == Cloud(cloud)]
        for cloud in [e.value for e in Cloud]
    ]

    zipped = itertools.zip_longest(*by_clouds)
    regions = itertools.chain.from_iterable(zipped)
    regions = [r for r in regions if r is not None]

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


def __num_tests(batches_of_tests):
    return sum(len(b) for b in batches_of_tests)


def __make_test_batches(batches_of_regions: List[List[CloudRegion]]):
    batches_of_tests = []
    for b in batches_of_regions:
        crossproduct_regionpairs = list(filter(lambda p: p[0] != p[1], product(b, b)))
        len_before = len(crossproduct_regionpairs)
        crossproduct_regionpairs = without_already_succeeded(crossproduct_regionpairs)
        if len(crossproduct_regionpairs) != len_before:
            logging.info(
                "Dropping %d region pairs that already succeeded",
                len_before - len(crossproduct_regionpairs),
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
        "as for example: AWS.us-east-1,AWS.us-east-2;AWS.us-west-1,GCP.us-west3."
        "If this is used, the other flags are ignored. Note that "
        'all these tests are run as one "batch" (in the terminology fo the other flags). '
        "If you want to run multiple batches of  tests that you specify, run this tool multiple times.",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=6,
        help="Number of regions to be tested simultaneously. "
        "Each cross-product combination will be tested with both directions of source/destination, but without intra-region (self-to-self) pairs. "
        "Thus, there will be batch_size * (batch_size-1)  tests in a batch)."
        "Only used if --region_pairs not used.",
    )
    parser.add_argument(
        "--max_batches",
        type=int,
        default=math.inf,
        help="Max number of batches of regions. "
        'Together with batch_size, this can be used to limit number of tests. Default indicates "do all". '
        "Only used if --region_pairs not used.",
    )

    parser.add_argument(
        "--one_cloud",
        type=Cloud,
        default=None,
        help='"GCP" or "AWS" means ignore tests that use a different cloud. '
        'Default (None) means "Don\'t ignore any clouds."'
        "Only used if --region_pairs not used.",
    )
    args = parser.parse_args()
    return args


def main():
    logging.info("Started at %s", datetime.datetime.now().isoformat())

    args = __command_line_args()
    batches = __batches_of_tests(
        args.batch_size,
        args.max_batches,
        args.one_cloud,
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
    set_cwd()
    main()
