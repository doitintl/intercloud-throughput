#!/usr/bin/env python
import logging

from cloud.clouds import (
    CloudRegion,
)
from graph.plot_chart import graph_full_testing_history
from history.attempted import (
    write_attempted_tests,
)
from test_steps.create_vms import create_vms
from test_steps.delete_vms import delete_vms
from test_steps.do_test import do_tests
from test_steps.define_batches_by_cli_args import setup_batches
from test_steps.utils import unique_regions
from util.utils import set_cwd, random_id, Timer, date_s

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def __batch_setup_test_teardown(region_pairs: list[tuple[CloudRegion, CloudRegion]], run_id):
    write_attempted_tests(region_pairs)
    logging.info("Will test %s", region_pairs)

    # VMs will still be cleaned up if launch or tests fail
    vm_region_and_address_infos = create_vms(region_pairs, run_id)
    logging.info(vm_region_and_address_infos)
    do_tests(run_id, vm_region_and_address_infos)
    delete_vms(run_id, unique_regions(region_pairs))


def main():
    logging.info("Started at %s", date_s())
    batches = setup_batches()

    run_id = random_id()
    logging.info("Run ID is %s", run_id)

    for batch in batches:
        __batch_setup_test_teardown(batch, run_id)

    graph_full_testing_history()


if __name__ == "__main__":
    with Timer("Full run"):
        set_cwd()
        main()
