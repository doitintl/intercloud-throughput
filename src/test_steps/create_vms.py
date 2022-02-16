import logging
import threading
from typing import Optional

from cloud.clouds import Region, Cloud
from history.attempted import write_missing_regions, write_failed_test
from test_steps.utils import env_for_singlecloud_subprocess, unique_regions
from util.subprocesses import run_subprocess
from util.utils import dedup, thread_timeout, Timer


def __create_vm(
    run_id_: str,
    cloud_region_: Region,
    vm_region_and_address_infos_inout: dict[Region, dict],
    machine_type=str,
):
    with Timer(f"__create_vm: {cloud_region_}"):
        logging.info("will launch a VM")  # reagion name in thread name
        env = env_for_singlecloud_subprocess(run_id_, cloud_region_)
        env["MACHINE_TYPE"] = machine_type
        process_stdout = run_subprocess(cloud_region_.script(), env)

        vm_address_info = process_stdout
        if vm_address_info[-1] == "\n":
            vm_address_info = vm_address_info[:-1]
        vm_address_infos = vm_address_info.split(",")

        vm_info = {
            "machine_type": machine_type,
            "address": vm_address_infos[0],
        }

        if len(vm_address_infos) > 1:
            vm_info["name"] = vm_address_infos[1]
            vm_info["zone"] = vm_address_infos[2]

        vm_region_and_address_infos_inout[cloud_region_] = vm_info


def __arrange_vms_by_region(
    regions_pairs: list[tuple[Region, Region]],
    region_to_vminfo: dict[Region, dict],
) -> list[tuple[tuple[Region, Optional[dict]], tuple[Region, Optional[dict]]]]:
    ret = []
    for pair in regions_pairs:
        src = pair[0]
        dst = pair[1]
        vm_info_src = region_to_vminfo.get(src)
        vm_info_dst = region_to_vminfo.get(dst)
        ret.append(((src, vm_info_src), (dst, vm_info_dst)))
    return ret


def create_vms(
    region_pairs_: list[tuple[Region, Region]],
    run_id: str,
    machine_types: dict[Cloud, str],
) -> list[tuple[tuple[Region, Optional[dict]], tuple[Region, Optional[dict]]]]:
    with Timer("create_vms"):
        vm_region_and_address_infos = {}
        threads = []
        regions_dedup = unique_regions(region_pairs_)
        logging.info(
            "VMs of types %s in %s regions: %s",
            "; ".join(f"{c.name}:{t}" for c, t in machine_types.items()),
            len(regions_dedup),
            regions_dedup,
        )
        for cloud_region in regions_dedup:
            thread = threading.Thread(
                name=f"thread-create-{cloud_region}",
                target=__create_vm,
                args=(
                    run_id,
                    cloud_region,
                    vm_region_and_address_infos,
                    machine_types[cloud_region.cloud],
                ),
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=thread_timeout)
            if thread.is_alive():
                logging.info("%s timed out", thread.name)

        if not vm_region_and_address_infos:
            logging.error("No VMs were created")

        regionwithvm_pairs = __arrange_vms_by_region(
            region_pairs_, vm_region_and_address_infos
        )

        __log_failure_to_create_vm(run_id,regionwithvm_pairs, machine_types)
        return regionwithvm_pairs


def __log_failure_to_create_vm(run_id:str,
    regionwithvm_pairs: list[tuple[tuple[Region, dict], tuple[Region, dict]]],
    machine_types: dict[Cloud, str],
):
    region_pairs_missing_a_vm = regionpairs_lacking_a_vm(regionwithvm_pairs)
    for fail_before_start in region_pairs_missing_a_vm:
        src_, dst_ = fail_before_start[0][0], fail_before_start[1][0]
        logging.error(
            "Failed because or more VMs was unavailable: Test %s,%s", src_, dst_
        )
        write_failed_test(run_id, src_, dst_)
    missing_regions = region_with_failed_vm(regionwithvm_pairs)
    if missing_regions:
        logging.info(
            "%d regions where no VM was successfully created %s",
            len(missing_regions),
            missing_regions,
        )
        write_missing_regions(missing_regions, machine_types)


def regionpairs_lacking_a_vm(
    regionwithvm_pairs: list[tuple[tuple[Region, dict], tuple[Region, dict]]]
) -> list[tuple[tuple[Region, dict], tuple[Region, dict]]]:
    return __regionpair_vm_success(regionwithvm_pairs)[0]


def regionpairs_with_both_vms(
    regionwithvm_pairs: list[tuple[tuple[Region, dict], tuple[Region, dict]]]
) -> list[tuple[tuple[Region, dict], tuple[Region, dict]]]:
    return __regionpair_vm_success(regionwithvm_pairs)[1]


def region_with_failed_vm(
    regionwithvm_pairs: list[tuple[tuple[Region, dict], tuple[Region, dict]]]
) -> list[Region]:
    return __regionpair_vm_success(regionwithvm_pairs)[2]


def __regionpair_vm_success(
    regionwithvm_pairs: list[tuple[tuple[Region, dict], tuple[Region, dict]]]
) -> tuple[
    list[tuple[tuple[Region, dict], tuple[Region, dict]]],
    list[tuple[tuple[Region, dict], tuple[Region, dict]]],
    list[Region],
]:
    missing_regions = []

    both_vms_exist: list[tuple[tuple[Region, dict], tuple[Region, dict]]]
    missing_one_or_more_vms: list[tuple[tuple[Region, dict], tuple[Region, dict]]]
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

    logging.info("%d tests where both VMs successfully created", len(both_vms_exist))

    return missing_one_or_more_vms, both_vms_exist, missing_regions
