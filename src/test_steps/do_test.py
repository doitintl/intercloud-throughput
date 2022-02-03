import json
import logging
import os
import threading
from typing import List, Tuple, Dict

from cloud.clouds import CloudRegion, Cloud, basename_key_for_aws_ssh
from history.attempted import write_failed_test
from history.results import write_results_for_run, combine_results
from util.subprocesses import run_subprocess
from util.utils import thread_timeout, Timer


def __do_test(
    run_id, src_dest: Tuple[Tuple[CloudRegion, Dict], Tuple[CloudRegion, Dict]]
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
                "Test %s result from %s to %s is %s", run_id, src[0], dst[0], process_stdout
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
    region_with_vminfo_pairs: List[
        Tuple[Tuple[CloudRegion, Dict], Tuple[CloudRegion, Dict]]
    ],
):
    with Timer("do_tests"):
        threads = []

        for p in region_with_vminfo_pairs:
            src = p[0][0]
            dest = p[1][0]
            thread_name = f"{src}-{dest}"
            logging.info(f"Will run test %s", thread_name)
            thread = threading.Thread(
                name=thread_name, target=__do_test, args=(run_id, p)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=thread_timeout)
            logging.info('Test "%s" done', thread.name)

        combine_results(run_id)
