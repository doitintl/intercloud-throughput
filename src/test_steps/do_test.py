import itertools
import json
import logging
import os
import threading
import time
from math import sqrt

from cloud.clouds import Region, Cloud, basename_key_for_aws_ssh
from history.attempted import write_failed_test
from history.results import (
    write_results_for_run,
    combine_results,
    analyze_test_count,
)
from test_steps.create_vms import regionpairs_with_both_vms
from util import utils
from util.subprocesses import run_subprocess
from util.utils import thread_timeout, Timer, dedup


class NoneAvailable(Exception):
    pass


def _regiondict_pairs_to_regionlist(
    pairs: list[tuple[tuple[Region, dict], tuple[Region, dict]]]
) -> list[Region]:
    region_pairs = [_regiondict_pair_to_region_pair(p) for p in pairs]
    return list(utils.shallow_flatten(region_pairs))


def _regiondict_pair_to_region_pair(
    p: tuple[tuple[Region, dict], tuple[Region, dict]]
) -> tuple[Region, Region]:
    return p[0][0], p[1][0]


def _regiondict_pair_to_regionlist(
    p: tuple[tuple[Region, dict], tuple[Region, dict]]
) -> list[Region]:
    region_pair = _regiondict_pair_to_region_pair(p)
    return list(itertools.chain(region_pair))


class Q:
    def __init__(
        self,
        region_pairs_with_valid_vms: list[
            tuple[tuple[Region, dict], tuple[Region, dict]]
        ],
    ):
        self.__lock = threading.Lock()

        self.__untested: list[tuple[tuple[Region, dict], tuple[Region, dict]]] = list(
            region_pairs_with_valid_vms
        )

        self.__now_under_test: list[
            tuple[tuple[Region, dict], tuple[Region, dict]]
        ] = []

    def num_untested(self):
        self.__lock.acquire()
        try:
            return len(self.__untested)
        finally:
            self.__lock.release()

    def is_done(self):
        self.__lock.acquire()
        try:
            none_left = not self.__untested
            none_still_under_test = not self.__now_under_test
            return none_left and none_still_under_test

        finally:
            self.__lock.release()

    def __get_suitable_pair(
        self,
    ) -> tuple[tuple[Region, dict], tuple[Region, dict]]:
        self.__lock.acquire()
        ret = None
        try:
            intest: list[Region] = _regiondict_pairs_to_regionlist(
                self.__now_under_test
            )
            for potential_testee in self.__untested:
                potential_testee_regionlist = _regiondict_pair_to_regionlist(
                    potential_testee
                )
                assert len(potential_testee_regionlist) == 2
                if all(r not in intest for r in potential_testee_regionlist):
                    self.__now_under_test.append(potential_testee)
                    self.__untested.remove(potential_testee)
                    ret = potential_testee
                    break

            return ret  # Can be none if none testable
        finally:
            self.__lock.release()

    def blocking_dequeue_one(self) -> tuple[tuple[Region, dict], tuple[Region, dict]]:
        while True:
            src_dest = self.__get_suitable_pair()
            if src_dest is None and self.num_untested():
                logging.info(
                    f"can't find a pair not currently under test in "
                    f"{self.num_untested()} not yet tested. ({len(self.__now_under_test)} now under test); retrying"
                )
                time.sleep(5)
                continue
            else:
                if not self.num_untested():
                    logging.info("done because queue is empty.")
                else:
                    assert (
                        src_dest
                    ), f"{threading.current_thread().name}; Q done {self.is_done()}, Untested {self.num_untested()}"
                    logging.info(
                        f"Will process {_regiondict_pair_to_region_pair(src_dest)}; {len(self.__untested)} left"
                    )
            return src_dest

    def one_test_done(self, src: tuple[Region, dict], dst: tuple[Region, dict]):
        self.__lock.acquire()
        try:
            logging.info(
                f"One test finished: {_regiondict_pair_to_region_pair((src, dst))}; {len(self.__untested)} left"
            )
            self.__now_under_test.remove((src, dst))
        finally:
            self.__lock.release()


def __deq_tests_and_run(run_id, q: Q):
    while not q.is_done():
        with Timer("dequeuing"):
            src_dest = q.blocking_dequeue_one()

        if src_dest is not None:
            src, dst = src_dest
            __do_one_test(src, dst, run_id, q)
        else:
            assert not q.num_untested()
            logging.info("No more untested available, exiting thread")
            break


def __do_one_test(src, dst, run_id, q):
    with Timer(f"Test {src[0]},{dst[0]}"):

        try:
            src_region_, src_vm_info = src
            dst_region_, dst_vm_info = dst
            logging.info("running test from %s to %s", src_region_, dst_region_)

            env = {
                "PATH": os.environ["PATH"],
                "RUN_ID": run_id,
                "SERVER_PUBLIC_ADDRESS": dst_vm_info["address"],
                "SERVER_CLOUD": dst_region_.cloud.name,
                "CLIENT_CLOUD": src_region_.cloud.name,
                "SERVER_REGION": dst_region_.region_id,
                "CLIENT_REGION": src_region_.region_id,
            }

            if src_region_.cloud == Cloud.AWS:
                env |= {
                    "CLIENT_PUBLIC_ADDRESS": src_vm_info["address"],
                    "BASE_KEYNAME": basename_key_for_aws_ssh,
                }
            elif src_region_.cloud == Cloud.GCP:
                try:
                    env |= {
                        "CLIENT_NAME": src_vm_info["name"],
                        "CLIENT_ZONE": src_vm_info["zone"],
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
            machine_types: dict[Cloud, str] = {
                r[0].cloud: r[1]["machine_type"] for r in (src, dst)
            }
            for c in Cloud:
                result_j[f"{c.name.lower()}_vm"] = machine_types.get(c)
            write_results_for_run(result_j, run_id, src_region_, dst_region_)
        except Exception as e:
            logging.exception(e)
            write_failed_test(run_id, src[0], dst[0])
        finally:
            q.one_test_done(src, dst)


def do_batch(
    run_id: str,
    region_with_vminfo_pairs: list[tuple[tuple[Region, dict], tuple[Region, dict]]],
):
    with Timer("do_tests"):
        assert region_with_vminfo_pairs, "Should not be empty"

        region_pairs_with_valid_vms = regionpairs_with_both_vms(
            region_with_vminfo_pairs
        )

        threads = []

        p: tuple[tuple[Region, dict], tuple[Region, dict]]
        q = Q(region_pairs_with_valid_vms)

        region_count = len(
            dedup(_regiondict_pairs_to_regionlist(region_with_vminfo_pairs))
        )
        # Reduce the contention where there are many regions
        thread_count = 2 * int(sqrt(region_count))
        assert thread_count >= 1

        logging.info("Will use %d test threads", thread_count)
        # This is very much not thread-bound, so
        for _ in range(thread_count):
            __start_thread(run_id, threads, q)

        for t in threads:
            t.join(timeout=thread_timeout)
            if t.is_alive():
                logging.info("%s timed out", t.name)

        combine_results(run_id)
        analyze_test_count()


thread_counter = 0


def __start_thread(run_id: str, threads: list[threading.Thread], q: Q):
    global thread_counter
    thread_counter += 1
    logging.info(f"Will run test-thread %s", f"testthread-{thread_counter}")
    thread = threading.Thread(
        name=f"testthread-{thread_counter}",
        target=__deq_tests_and_run,
        args=(run_id, q),
    )
    threads.append(thread)
    thread.start()
