import argparse

import datetime
import itertools
import json
import logging
import math
import os
import random
import shutil
import string
import threading
from collections import Counter

from typing import List, Dict, Tuple, Callable, Optional

from history.attempted import without_already_attempted, write_attempted_tests
from cloud.clouds import (
    Cloud,
    CloudRegion,
    interregion_distance,
    get_regions,
    key_for_aws_ssh_basename,
    get_cloud_region,
)
from history.results import combine_results_to_csv

from util.subprocesses import run_subprocess
from util.utils import dedup

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def __env_for_singlecloud_subprocess(run_id, cloud_region):
    return {
        "PATH": os.environ["PATH"],
        "REGION": cloud_region.region_id,
        "RUN_ID": run_id,
    } | cloud_region.env()


def __create_vms(
    regions: List[CloudRegion], run_id: str
) -> List[Tuple[CloudRegion, Dict]]:
    # TODO Improve thread use with ThreadPoolExecutor and futures
    def create_vm(
        run_id_: str,
        cloud_region_: CloudRegion,
        vm_region_and_address_infos_inout: List[Tuple[CloudRegion, Dict]],
    ):
        logging.info("Will launch a VM in %s", cloud_region_)
        env = __env_for_singlecloud_subprocess(run_id_, cloud_region_)

        process_stdout = run_subprocess(cloud_region_.script(), env)
        vm_addresses = {}
        vm_address_info = process_stdout
        if vm_address_info[-1] == "\n":
            vm_address_info = vm_address_info[:-1]
        vm_address_infos = vm_address_info.split(",")
        vm_addresses["address"] = vm_address_infos[0]
        if len(vm_address_infos) > 1:
            vm_addresses["name"] = vm_address_infos[1]
            vm_addresses["zone"] = vm_address_infos[2]

        vm_region_and_address_infos_inout.append((cloud_region_, vm_addresses))

    def sort_addr_by_region(
        vm_region_and_address_infos: List[Tuple[CloudRegion, Dict]],
        regions: List[CloudRegion],
    ):
        ret = []
        for region in regions:
            for_this_region = [t for t in vm_region_and_address_infos if t[0] == region]

            if len(for_this_region) != 1:
                logging.error(
                    "For region %s found this data %s. Had these VMs %s}",
                    region,
                    for_this_region,
                    vm_region_and_address_infos,
                )
            if for_this_region:
                ret.append(for_this_region[0])
        return ret

    vm_region_and_address_infos = []
    threads = []
    regions_dedup = dedup(regions)
    for cloud_region in regions_dedup:
        thread = threading.Thread(
            name=f"create-{cloud_region}",
            target=create_vm,
            args=(run_id, cloud_region, vm_region_and_address_infos),
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
        logging.info('create_vm in "%s" done', thread.name)

    ret = sort_addr_by_region(vm_region_and_address_infos, regions)
    return ret


def __do_tests(
    run_id: str,
    vm_region_and_address_infos: List[Tuple[CloudRegion, Dict]],
):
    results_dir_for_this_runid = f"./result-files-one-run/results-{run_id}"
    try:
        os.mkdir(results_dir_for_this_runid)
    except FileExistsError:
        pass

    def run_test(run_id, src: Tuple[CloudRegion, Dict], dst: Tuple[CloudRegion, Dict]):
        logging.info("running test from %s to %s", src, dst)
        src_region_, src_addr_infos = src
        dst_region_, dst_addr_infos = dst
        env = {
            "PATH": os.environ["PATH"],
            "RUN_ID": run_id,
            "SERVER_PUBLIC_ADDRESS": dst_addr_infos["address"],
            "SERVER_CLOUD": dst_region_.cloud.name,
            "CLIENT_CLOUD": src_region_.cloud.name,
            "SERVER_REGION": dst_region_.region_id,
            "CLIENT_REGION": src_region_.region_id,
        }
        if src_region.cloud == Cloud.AWS:
            env |= {
                "CLIENT_PUBLIC_ADDRESS": src_addr_infos["address"],
                "BASE_KEYNAME": key_for_aws_ssh_basename,
            }
        elif src_region.cloud == Cloud.GCP:
            try:
                env |= {
                    "CLIENT_NAME": src_addr_infos["name"],
                    "CLIENT_ZONE": src_addr_infos["zone"],
                }
            except KeyError as ke:
                logging.error("{src_addr_infos=}")
                raise ke

        else:
            raise Exception(f"Implement {src_region}")
        non_str = [(k, v) for k, v in env.items() if type(v) != str]
        assert not non_str, non_str

        script = src_region.script_for_test_from_region()
        process_stdout = run_subprocess(script, env)
        logging.info(
            "Test %s result from %s to %s is %s", run_id, src, dst, process_stdout
        )
        test_result = process_stdout + "\n"
        result_j = json.loads(test_result)
        result_j["distance"] = interregion_distance(src_region_, dst_region_)

        results_for_one_run_file = (
            f"{results_dir_for_this_runid}/results-{src_region_}-to-{dst_region_}.json"
        )
        # We write separate files for each test to avoid race conditions, since tests happen in parallel.
        with open(
            results_for_one_run_file,
            "w",
        ) as f:
            json.dump(result_j, f)
            logging.info("Wrote %s", results_for_one_run_file)

    vm_pairs: List[Tuple[Tuple[CloudRegion, Dict], Tuple[CloudRegion, Dict]]]

    assert len(vm_region_and_address_infos) % 2 == 0, (
        f"Must provide an even number of region in pairs for tests:"
        f" was length {len(vm_region_and_address_infos)}: {vm_region_and_address_infos}"
    )

    vm_pairs = [
        (vm_region_and_address_infos[i], vm_region_and_address_infos[i + 1])
        for i in range(0, len(vm_region_and_address_infos), 2)
    ]

    logging.info(
        "%s tests and %s regions ",
        len(vm_pairs),
        len(vm_region_and_address_infos),
    )
    threads = []

    for src, dest in vm_pairs:
        src_region = src[0]
        dst_region = dest[0]
        thread_name = f"{src_region}-{dst_region}"
        logging.info(f"Will run test %s", thread_name)
        thread = threading.Thread(
            name=thread_name, target=run_test, args=(run_id, src, dest)
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
        logging.info('"%s" done', thread.name)

    combine_results_to_csv(results_dir_for_this_runid)
    shutil.rmtree(results_dir_for_this_runid)


def __regionpairs() -> List[Tuple[CloudRegion, CloudRegion]]:
    test_results_: List[Dict]

    all_regions: List[CloudRegion]
    all_regions = get_regions()
    all_pairs_with_intraregion = itertools.product(all_regions, all_regions)
    all_pairs_no_intraregion = [p for p in all_pairs_with_intraregion if p[0] != p[1]]

    return all_pairs_no_intraregion


def __delete_vms(run_id, regions: List[CloudRegion]):
    def delete_aws_vm(aws_cloud_region: CloudRegion):
        assert aws_cloud_region.cloud == Cloud.AWS, aws_cloud_region
        logging.info(
            "Will delete EC2 VMs from run-id %s in %s", run_id, aws_cloud_region
        )
        env = __env_for_singlecloud_subprocess(run_id, aws_cloud_region)
        script = cloud_region.deletion_script()
        _ = run_subprocess(script, env)

    # First, AWS
    aws_regions = [r for r in regions if r.cloud == Cloud.AWS]
    threads = []

    for cloud_region in aws_regions:
        thread = threading.Thread(
            name=f"delete-{cloud_region}", target=delete_aws_vm, args=(cloud_region,)
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
        logging.info("%s done", thread.name)

    # Now GCP

    gcp_regions = [r for r in regions if r.cloud == Cloud.GCP]

    if gcp_regions:
        cloud_region = gcp_regions[
            0
        ]  # One arbitrary region, for getting values for GCP.
        logging.info("Will delete GCE VMs from run-id %s", run_id)
        env = __env_for_singlecloud_subprocess(run_id, cloud_region)
        _ = run_subprocess(cloud_region.deletion_script(), env)


def __setup_and_tests_and_teardown(run_id: str, regions: List[CloudRegion]):
    """regions taken pairwise"""
    # Because we launch VMs and runs tests multithreaded, if one launch fails or one tests fails, run_tests() will not thrown an Exception.
    # So, VMs will still be cleaned up
    assert len(regions) % 2 == 0, f"Expect pairs {regions}"

    vm_region_and_address_infos = __create_vms(regions, run_id)
    logging.info(vm_region_and_address_infos)
    __do_tests(run_id, vm_region_and_address_infos)
    __delete_vms(run_id, regions)


def test_region_pairs(region_pairs: List[Tuple[CloudRegion, CloudRegion]], run_id):
    write_attempted_tests(region_pairs)
    logging.info("Will test %s", region_pairs)
    regions = list(itertools.chain(*region_pairs))
    __setup_and_tests_and_teardown(run_id, regions)


def most_frequent_region_first_func(
    region_pairs,
) -> Callable[[Tuple[CloudRegion, CloudRegion]], Tuple[int, str]]:
    """:return a function that will allow sorting in descending order of freq of appearance
    of a CloudRegion, with the name of the CloudRegion as a tiebreaker"""
    sources = [r[0] for r in region_pairs]
    dests = [r[1] for r in region_pairs]
    both = sources + dests
    counts = Counter(both)

    def key_func(pair: Tuple[CloudRegion, CloudRegion]) -> Tuple[int, str]:
        descending_freq = -1 * (counts[pair[0]] + counts[pair[1]])
        return (descending_freq, repr(pair))

    return key_func


def __parse_region_pairs(
    region_pairs: str,
) -> Optional[List[Tuple[CloudRegion, CloudRegion]]]:
    if not region_pairs:
        return None

    def str_to_reg(s):
        dash_idx = s.index("-")
        if dash_idx == -1:
            raise ValueError(f"{s} not a value cloud-region string")
        cloud_s = s[0:dash_idx]
        region_s = s[dash_idx + 1 :]
        return get_cloud_region(Cloud(cloud_s), region_s)

    pairs_s = region_pairs.split(";")
    pairs_str_2item_list = [p.split(",") for p in pairs_s]
    pairs_regions = [(str_to_reg(p[0]), str_to_reg(p[1])) for p in pairs_str_2item_list]
    return pairs_regions


def __batches_of_tests(
    batch_size: int,
    num_batches: int,
    only_this_cloud: Cloud,
    preselected_region_pairs: List[Tuple[CloudRegion, CloudRegion]],
):
    if preselected_region_pairs:
        region_pairs = preselected_region_pairs
    else:
        region_pairs = __regionpairs()
        region_pairs = without_already_attempted(region_pairs)
        region_pairs = sorted(
            region_pairs, key=most_frequent_region_first_func(region_pairs)
        )

    if only_this_cloud:
        region_pairs = [
            r
            for r in region_pairs
            if r[0].cloud == only_this_cloud and r[1].cloud == only_this_cloud
        ]

    batches = [
        region_pairs[i : i + batch_size]
        for i in range(0, len(region_pairs), batch_size)
    ]
    if num_batches>math.inf:
        batches = batches[:num_batches]
    tot_len = sum(len(g) for g in batches)
    logging.info(
        f"After limiting number of tests, where specified, for batch size/count and for specific cloud, running {tot_len} tests"
    )
    return batches


def main():

    logging.info("Started at %s", datetime.datetime.now().isoformat())

    parser = argparse.ArgumentParser(description="", allow_abbrev=True)
    parser.add_argument(
        "--region_pairs",
        type=str,
        default=None,
        help="Pairs to test, where "
        "cloud and region names are separated by dash; source and destination are separated by comma; "
        "and pairs are separated by semicolon, "
        "as for example: AWS-us-east-1,AWS-us-east-2;AWS-us-west-1,GCP-us-west3",
    )
    parser.add_argument("--batch_size", type=int, default=6,
                        help='Size of batch of tests to be run in parallels. Together with num_batches, this can limit number of tests")',
                        )

    parser.add_argument(
        "--num_batches",
        type=int,
        default=math.inf,
        help='Max number of batches. Together with batch_size, this can limit number of tests. Default indicates "do all tests")',
    )
    parser.add_argument(
        "--only_this_cloud",
        type=Cloud,
        default=None,
        help='"GCP" or "AWS". Default (None) means "Do them all"',
    )

    args = parser.parse_args()
    region_pairs = __parse_region_pairs(args.region_pairs)

    batches = __batches_of_tests(
        args.batch_size, args.num_batches, args.only_this_cloud, region_pairs
    )
    run_id = "".join(random.choices(string.ascii_lowercase, k=4))

    for batch in batches:
        test_region_pairs(batch, run_id)




if __name__ == "__main__":
    main()
