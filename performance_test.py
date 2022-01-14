import datetime
import json
import logging
import os
import random
import string
import sys
import threading
from typing import List, Dict, Tuple, Iterable
import itertools
import shutil

from clouds.clouds import Cloud, CloudRegion, get_cloud_region, interregion_distance
from util.subprocesses import run_subprocess

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


def create_vms(regions, run_id) -> List[Tuple[CloudRegion, Dict]]:
    # TODO Improve thread use with ThreadPoolExecutor and futures
    def create_vm(
        run_id: str,
        cloud_region: CloudRegion,
        vm_region_and_address_infos_inout: List[Tuple[CloudRegion, Dict]],
    ):
        logging.info("Will launch a VM in %s", cloud_region)
        env = __env_for_singlecloud_subprocess(run_id, cloud_region)

        process_stdout = run_subprocess(cloud_region.script(), env)
        vm_addresses = {}
        vm_address_info = process_stdout
        if vm_address_info[-1] == "\n":
            vm_address_info = vm_address_info[:-1]
        vm_address_infos = vm_address_info.split(",")
        vm_addresses["address"] = vm_address_infos[0]
        if len(vm_address_infos) > 1:
            vm_addresses["name"] = vm_address_infos[1]
            vm_addresses["zone"] = vm_address_infos[2]

        vm_region_and_address_infos_inout.append((cloud_region, vm_addresses))

    vm_region_and_address_infos = []
    threads = []
    for cloud_region in regions:
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


def run_tests(
    run_id: str,
    crossproduct: bool,
    vm_region_and_address_infos: List[Tuple[CloudRegion, Dict]],
):
    results_dir_for_this_runid = f"./results-{run_id}"
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
                "BASE_KEYNAME": "intercloudperfkey",
            }
        elif src_region.cloud == Cloud.GCP:
            env |= {
                "CLIENT_NAME": src_addr_infos["name"],
                "CLIENT_ZONE": src_addr_infos["zone"],
            }
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

        # We write separate files for each test to avoid race conditions, since tests happen in parallel.
        with open(
            f"{results_dir_for_this_runid}/results-{src_region_}-to-{dst_region_}.json",
            "w",
        ) as f:
            json.dump(result_j, f)

    vm_pairs: List[Tuple[Tuple[CloudRegion, Dict], Tuple[CloudRegion, Dict]]]
    if crossproduct:
        vm_pairs_all = list(
            itertools.product(vm_region_and_address_infos, vm_region_and_address_infos)
        )
        vm_pairs = list(filter(lambda pair: pair[0][0] != pair[1][0],vm_pairs_all))
        logging.info("Removed %d identical VM pairs from the cross product", len(vm_pairs_all)-len(vm_pairs))
    else:
        assert (
            len(vm_region_and_address_infos) % 2 == 0
        ), f"Must provide an even number of regions. They will be taken in pairs for tests: {vm_region_and_address_infos}"
        vm_pairs = [
            (vm_region_and_address_infos[i], vm_region_and_address_infos[i + 1])
            for i in range(0, len(vm_region_and_address_infos), 2)
        ]

    logging.info(
        "Testing %s. %s tests and %s regions ",
        "crossproduct" if crossproduct else "specified pair",
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

    filenames = os.listdir(results_dir_for_this_runid)
    with open("./results.jsonl", "a") as outfile:
        for fname in filenames:
            with open(results_dir_for_this_runid + os.sep + fname) as infile:
                one_json = infile.read()
                outfile.write(one_json + "\n")
    shutil.rmtree(results_dir_for_this_runid)


def delete_vms(run_id, regions: List[CloudRegion]):
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


def do_all(run_id: str, crossproduct: bool, regions: List[CloudRegion]):
    """

    :param crossproduct: If true, will test each possible pair of CloudRegions. (Not same-to-same, however).
    If False, will take the list of region in pairs, and test from the first to the second
    in each pair.
    """
    # Because we launch VMs and runs tests multithreaded, if one launch fails or one tests fails, run_tests() will not thrown an Exception.
    # So, VMs will still be cleaned up
    vm_region_and_address_infos = create_vms(regions, run_id)
    logging.info(vm_region_and_address_infos)
    run_tests(run_id, crossproduct, vm_region_and_address_infos)
    delete_vms(run_id, regions)


def main():
    logging.info("Started at %s", datetime.datetime.now().isoformat())
    run_id = "".join(random.choices(string.ascii_lowercase, k=4))
    if len(sys.argv) > 1:
        gcp_project = sys.argv[1]
    else:
        gcp_project = None  # use default

    regions = [(Cloud.AWS, "us-east-2"), (Cloud.GCP, "us-west3", gcp_project)]
    crossproduct = False
    do_all(run_id, crossproduct, [get_cloud_region(*r) for r in regions])


if __name__ == "__main__":
    main()
