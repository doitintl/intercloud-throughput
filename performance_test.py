import logging
import os
import random
import string
import sys
import threading
from typing import List, Dict, Tuple
import itertools
import shutil

from clouds.clouds import Cloud, CloudRegion
from utils.subprocesses import run_subprocess

logging.basicConfig(encoding='utf-8', level=logging.DEBUG)


def __env_for_singlecloud_subprocess(run_id, cloud_region):
    return {"PATH": os.environ["PATH"],
            "REGION": cloud_region.region,
            "RUN_ID": run_id} | cloud_region.env()


def create_vms(regions, run_id) -> List[Tuple[CloudRegion, Dict]]:
    # TODO Improve thread use with ThreadPoolExecutor and futures
    def create_vm(run_id: str, cloud_region: CloudRegion,
                  vm_region_and_address_infos_inout: List[Tuple[CloudRegion, Dict]]):
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

    ret = []
    threads = []
    for cloud_region in regions:
        thread = threading.Thread(name=f"{cloud_region}", target=create_vm,
                                  args=(run_id, cloud_region, ret))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
        logging.info('"%s" done', thread.name)

    return ret


# Because this runs tests multithreaded, if one fails, run_tests() will not thrown an Exception.
# This is good in case the VMs where launched but a test fails, as VMs will still be cleaned up
def run_tests(run_id, vm_region_and_address_infos: List[Tuple[CloudRegion, Dict]]):
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
            "SERVER_REGION": dst_region_.region,
            "CLIENT_REGION": src_region_.region,
        }
        if src_region.cloud == Cloud.AWS:
            env["CLIENT_PUBLIC_ADDRESS"] = src_addr_infos["address"]
        elif src_region.cloud == Cloud.GCP:
            env["CLIENT_NAME"] = src_addr_infos["name"]
            env["CLIENT_ZONE"] = src_addr_infos["zone"]
        else:
            raise Exception(f"Implement {src_region}")
        non_str = [(k, v) for k, v in env.items() if type(v) != str]
        assert not non_str, non_str

        script = src_region.script_for_test_from_region()
        process_stdout = run_subprocess(script, env)
        logging.info("Test %s result from %s to %s is %s", run_id, src, dst, process_stdout)
        test_result = process_stdout + "\n"

        # We write separate files for each test to avoid race conditions, since tests happen in parallel.
        with open(f'{results_dir_for_this_runid}/results-{src_region_}-to-{dst_region_}.json', 'w') as f:
            f.write(test_result)


    threads = []
    for src, dest in itertools.product(vm_region_and_address_infos, vm_region_and_address_infos):
        src_region = src[0]
        dst_region = dest[0]

        thread = threading.Thread(name=f"{src_region}-{dst_region}", target=run_test,
                                  args=(run_id, src, dest))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
        logging.info('"%s" done', thread.name)

    filenames = os.listdir(results_dir_for_this_runid)
    with open('./results.jsonl', 'a') as outfile:
        for fname in filenames:
            with open(results_dir_for_this_runid+os.sep+fname) as infile:
                outfile.write(infile.read())
    shutil.rmtree(results_dir_for_this_runid)


def delete_vms(run_id, regions: List[CloudRegion]):
    def delete_aws_vm(aws_cloud_region: CloudRegion):
        assert aws_cloud_region.cloud == Cloud.AWS, aws_cloud_region
        logging.info("Will delete VMs from run-id %s in %s", run_id, aws_cloud_region)
        env = __env_for_singlecloud_subprocess(run_id, aws_cloud_region)
        script = cloud_region.deletion_script()
        _ = run_subprocess(script, env)

    # First, Aws
    aws_regions = [r for r in regions if r.cloud == Cloud.AWS]
    threads = []

    for cloud_region in aws_regions:
        thread = threading.Thread(name=f"{cloud_region}", target=delete_aws_vm,
                                  args=(cloud_region,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
        logging.info('"%s" done', thread.name)

    # Now GCP
    gcp_regions = {r for r in regions if r.cloud == Cloud.GCP}

    if gcp_regions:
        cloud_region = next(iter(gcp_regions))  # One arbitrary region
        logging.info("Will delete VMs from run-id %s in %s", run_id, cloud_region.cloud)
        env = __env_for_singlecloud_subprocess(run_id, cloud_region)
        _ = run_subprocess(cloud_region.deletion_script(), env)


def do_all(run_id: str, regions: List[CloudRegion]):
    vm_region_and_address_infos = create_vms(regions, run_id)
    logging.info(vm_region_and_address_infos)
    run_tests(run_id, vm_region_and_address_infos)
    delete_vms(run_id, regions)


def main():
    run_id = ''.join(random.choices(string.ascii_lowercase, k=4))
    if len(sys.argv) > 1:
        gcp_project = sys.argv[1]
    else:
        gcp_project = "joshua-playground"

    regions = [
        (Cloud.GCP, "us-east1", gcp_project),
        (Cloud.AWS, "us-east-1")
    ]
    do_all(run_id, [CloudRegion(*r) for r in regions])


if __name__ == '__main__':
    main()
