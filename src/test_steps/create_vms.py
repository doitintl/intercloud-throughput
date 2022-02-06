import logging
import threading
from typing import Optional

from cloud.clouds import CloudRegion
from history.attempted import write_missing_regions
from test_steps.utils import env_for_singlecloud_subprocess, unique_regions
from util.subprocesses import run_subprocess
from util.utils import dedup, thread_timeout, Timer


def __create_vm(
    run_id_: str,
    cloud_region_: CloudRegion,
    vm_region_and_address_infos_inout: dict[CloudRegion, dict],
):
    with Timer(f"__create_vm: {cloud_region_}"):
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
    regions_pairs: list[tuple[CloudRegion, CloudRegion]],
    region_to_vminfo: dict[CloudRegion, dict],
) -> list[
    tuple[tuple[CloudRegion, Optional[dict]], tuple[CloudRegion, Optional[dict]]]
]:
    ret = []
    for pair in regions_pairs:
        src = pair[0]
        dst = pair[1]
        vm_info_src = region_to_vminfo.get(src)
        vm_info_dst = region_to_vminfo.get(dst)
        ret.append(((src, vm_info_src), (dst, vm_info_dst)))
    return ret


def create_vms(
    region_pairs_: list[tuple[CloudRegion, CloudRegion]], run_id: str
) -> list[
    tuple[tuple[CloudRegion, Optional[dict]], tuple[CloudRegion, Optional[dict]]]
]:
    with Timer("create_vms"):
        vm_region_and_address_infos = {}
        threads = []
        regions_dedup = unique_regions(region_pairs_)
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
            logging.error("No VMs were created")

        regionwithvm_pairs = __arrange_vms_by_region(
            region_pairs_, vm_region_and_address_infos
        )

        return regionwithvm_pairs


def find_regions_lacking_a_vm(
    regionwithvm_pairs: list[tuple[tuple[CloudRegion, dict], tuple[CloudRegion, dict]]]
) -> tuple[
    list[tuple[tuple[CloudRegion, dict], tuple[CloudRegion, dict]]],
    list[tuple[tuple[CloudRegion, dict], tuple[CloudRegion, dict]]],
]:
    missing_regions = []

    both_vms_exist: list[tuple[tuple[CloudRegion, dict], tuple[CloudRegion, dict]]]
    missing_one_or_more_vms: list[
        tuple[tuple[CloudRegion, dict], tuple[CloudRegion, dict]]
    ]
    both_vms_exist = []
    missing_one_or_more_vms = []
    for regionwithvm_pair in regionwithvm_pairs:
        skip = False
        for i in [0, 1]:
            if regionwithvm_pair[i][1] is None:
                missing_regions.append(regionwithvm_pair[i][0])
                skip = True
        if skip:
            missing_one_or_more_vms.append(regionwithvm_pair)
        else:
            both_vms_exist.append(regionwithvm_pair)

    missing_regions = dedup(missing_regions)
    if missing_regions:
        logging.info(
            "%d regions where no VM was successfully created %s",
            len(missing_regions),
            missing_regions,
        )
        write_missing_regions(*missing_regions)

    logging.info("%d tests where both VMs successfully created", len(both_vms_exist))
    return both_vms_exist, missing_one_or_more_vms
