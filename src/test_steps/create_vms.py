import logging
import threading
from typing import List, Tuple, Dict

from cloud.clouds import CloudRegion
from history.attempted import write_failed_test
from test_steps.utils import env_for_singlecloud_subprocess, unique_regions
from util.subprocesses import run_subprocess
from util.utils import dedup, thread_timeout


def __create_vm(
    run_id_: str,
    cloud_region_: CloudRegion,
    vm_region_and_address_infos_inout: Dict[CloudRegion, Dict],
):
    logging.info("Will launch a VM in %s", cloud_region_)
    env = env_for_singlecloud_subprocess(run_id_, cloud_region_)

    process_stdout = run_subprocess(cloud_region_.script(), env)

    vm_info = {}
    vm_address_info = process_stdout
    if vm_address_info[-1] == "\n":
        vm_address_info = vm_address_info[:-1]
    vm_address_infos = vm_address_info.split(",")
    vm_info["address"] = vm_address_infos[0]
    if len(vm_address_infos) > 1:
        vm_info["name"] = vm_address_infos[1]
        vm_info["zone"] = vm_address_infos[2]

    vm_region_and_address_infos_inout[cloud_region_] = vm_info


def __arrange_vms_by_region(
    regions_pairs: List[Tuple[CloudRegion, CloudRegion]],
    region_to_vminfo: Dict[CloudRegion, Dict],
) -> List[Tuple[Tuple[CloudRegion, Dict], Tuple[CloudRegion, Dict]]]:
    ret = []
    for pair in regions_pairs:
        vm_info_src = region_to_vminfo.get(pair[0])
        vm_info_dst = region_to_vminfo.get(pair[0])
        src_region = pair[0]
        dst_region = pair[1]
        ret.append(((src_region, vm_info_src), (dst_region, vm_info_dst)))
    return ret


def create_vms(
    region_pairs: List[Tuple[CloudRegion, CloudRegion]], run_id: str
) -> List[Tuple[Tuple[CloudRegion, Dict], Tuple[CloudRegion, Dict]]]:
    # TODO Improve thread use with ThreadPoolExecutor and futures

    vm_region_and_address_infos = {}
    threads = []
    regions_dedup = unique_regions(region_pairs)
    for cloud_region in regions_dedup:
        thread = threading.Thread(
            name=f"create-{cloud_region}",
            target=__create_vm,
            args=(run_id, cloud_region, vm_region_and_address_infos),
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join(timeout=thread_timeout)
        logging.info('create_vm in "%s" done', thread.name)

    if not vm_region_and_address_infos:
        raise ValueError("No VMs were created")

    regionwithvm_pairs = __arrange_vms_by_region(
        region_pairs, vm_region_and_address_infos
    )

    ret = __filter_regions_with_no_vms(regionwithvm_pairs)

    return ret


def __filter_regions_with_no_vms(regionwithvm_pairs:List[Tuple[Tuple[CloudRegion, Dict], Tuple[CloudRegion, Dict]]])->List[Tuple[Tuple[CloudRegion, Dict], Tuple[CloudRegion, Dict]]]:
    missing_regions = []
    skip_tests:List[Tuple[ CloudRegion, CloudRegion]]
    skip_tests= []

    ret = []
    for regionwithvm_pair in regionwithvm_pairs:
        skip = False
        for i in [0, 1]:
            if not regionwithvm_pair[i][1]:
                missing_regions.append(regionwithvm_pair[i])
                skip = True
        if skip:
            skip_tests.append((regionwithvm_pair[0][0], regionwithvm_pair[1][0]))
        else:
            ret.append(regionwithvm_pair)

    missing_regions = dedup(missing_regions)
    if missing_regions:
        logging.info("Regions where no VM was successfully created %s", missing_regions)
        logging.info(
            "Tests to skip because VM unavailable on at least one region: %s", skip_tests
        )
        for tst in skip_tests:
            write_failed_test(*tst)

    logging.info("Tests where both VMs successfully created %d", len(ret))
    return ret