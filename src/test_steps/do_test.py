import json
import logging
import os
import threading

from cloud.clouds import CloudRegion, Cloud, basename_key_for_aws_ssh
from history.attempted import write_failed_test
from history.results import (
    write_results_for_run,
    combine_results,
    analyze_test_count,
)
from test_steps.create_vms import find_regions_lacking_a_vm
from util.subprocesses import run_subprocess
from util.utils import thread_timeout, Timer


def __do_test(
    run_id, src_dest: tuple[tuple[CloudRegion, dict], tuple[CloudRegion, dict]]
):
    src, dst = src_dest
    src_region_, src_addr_infos = src
    dst_region_, dst_addr_infos = dst
    with Timer(f"__do_test:{src_region_},{dst_region_}"):
        try:
            logging.info("running test from %s to %s", src_region_, dst_region_)

            env = {
                "PATH": os.environ["PATH"],
                "RUN_ID": run_id,
                "SERVER_PUBLIC_ADDRESS": dst_addr_infos["address"],
                "SERVER_CLOUD": dst_region_.cloud.name,
                "CLIENT_CLOUD": src_region_.cloud.name,
                "SERVER_REGION": dst_region_.region_id,
                "CLIENT_REGION": src_region_.region_id,
            }

            if src_region_.cloud == Cloud.AWS:
                env |= {
                    "CLIENT_PUBLIC_ADDRESS": src_addr_infos["address"],
                    "BASE_KEYNAME": basename_key_for_aws_ssh,
                }
            elif src_region_.cloud == Cloud.GCP:
                try:
                    env |= {
                        "CLIENT_NAME": src_addr_infos["name"],
                        "CLIENT_ZONE": src_addr_infos["zone"],
                    }
                except KeyError as ke:
                    logging.error("{src_addr_infos=}")
                    raise ke

            else:
                raise Exception(
                    f"Implement {src_region_.cloud} (region {src_region_} to region {dst_region_} )"
                )

            script = src_region_.script_for_test_from_region()

            process_stdout = run_subprocess(script, env)

            logging.info(
                "Test %s result from %s to %s is %s",
                run_id,
                src[0],
                dst[0],
                process_stdout,
            )
            test_result = process_stdout + "\n"
            result_j = json.loads(test_result)

            write_results_for_run(result_j, run_id, src_region_, dst_region_)
        except Exception as e:
            logging.error("Exception %s", e)
            write_failed_test(src[0], dst[0])
            raise e


def do_tests(
    run_id: str,
    region_with_vminfo_pairs: list[
        tuple[tuple[CloudRegion, dict], tuple[CloudRegion, dict]]
    ],
):
    with Timer("do_tests"):
        (
            region_pairs_with_valid_vms,
            region_pairs_missing_a_vm,
        ) = find_regions_lacking_a_vm(region_with_vminfo_pairs)
        for fail_before_start in region_pairs_missing_a_vm:
            src_, dst_ = fail_before_start[0][0], fail_before_start[1][0]
            logging.error(
                "Failed because or more VMs was unavailable: Test %s,%s", src_, dst_
            )
            write_failed_test(src_, dst_)

        threads = []

        p: tuple[tuple[CloudRegion, dict], tuple[CloudRegion, dict]]
        for p in region_pairs_with_valid_vms:
            src, dest = p[0][0], p[1][0]
            assert all(p[i][1] for i in [0, 1]), "Should have vm info for each %s" % p
            thread_name = f"{src}-{dest}"
            logging.info(f"Will run test %s", thread_name)
            thread = threading.Thread(
                name=thread_name, target=__do_test, args=(run_id, p)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=thread_timeout)
            if thread.is_alive():
                logging.info("%s timed out", thread)
            logging.info('Test "%s" done', thread.name)

        combine_results(run_id)
        analyze_test_count()
