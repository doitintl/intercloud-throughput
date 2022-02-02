import argparse
import datetime
import logging
import math
from itertools import product
from typing import List, Tuple, Optional

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
    # Because we launch VMs and runs tests multithreaded, if one launch fails or one tests fails, run_tests() will not thrown an Exception.
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
            raise ValueError(f"{s} not a dot-separated cloud-region string")
        return get_region(*cloud_and_region)

    pairs_s: List[str] = region_pairs.split(";")
    test_pairs: List[List[str]] = [p.split(",") for p in pairs_s]
    if not all(len(pair) == 2 for pair in test_pairs):
        raise ValueError(f"{pairs_s} is not comma-separated cloud-region pairs")
    pairs_regions = [(parse_region(p[0]), parse_region(p[1])) for p in test_pairs]
    return pairs_regions


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
        # regions.sort(key=ascending_freq(regions)) TODO ascending freq of already-done tests
        batches_of_regions = list(chunks(regions,regions_per_batch))


        if max_batches < math.inf:
            batches_of_regions = batches_of_regions[:max_batches]
        batches_of_tests: List[List[Tuple[CloudRegion, CloudRegion]]]
        batches_of_tests = []
        for b in batches_of_regions:
            crossproduct_regionpairs = list(filter(lambda p: p[0] != p[1], product(b, b)))
            sz_before=len(crossproduct_regionpairs)
            crossproduct_regionpairs = without_already_succeeded(
                crossproduct_regionpairs
            )
            if len(crossproduct_regionpairs)!=sz_before:
                logging.info("Dropping %d region pairs that already succeeded" , sz_before- len(crossproduct_regionpairs) )
            if crossproduct_regionpairs:# Might have already done all these tests
                batches_of_tests.append(crossproduct_regionpairs)

    logging.info(
        f"Will run %d tests in %d batches",
        sum(len(b) for b in batches_of_tests),
        len(batches_of_tests),
    )
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

    for batch in batches:
        test_batch(batch, run_id)

    graph_full_testing_history()


if __name__ == "__main__":
    set_cwd()
    main()
