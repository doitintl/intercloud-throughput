#!/usr/bin/env python
import logging

from graph.plot_chart import graph_full_testing_history
from test_steps import batching
from util.utils import (
    set_cwd,
    random_id,
    Timer,
    process_starttime_iso,
    init_logger,
    process_starttime,
)

init_logger()


def main():

    batches, machine_types = batching.setup_batches()

    run_id = random_id()
    logging.info("Run ID is %s", run_id)

    for batch in batches:
        batching.batch_setup_test_teardown(run_id, batch, machine_types)

    graph_full_testing_history()


if __name__ == "__main__":
    logging.info("Starting at %s", process_starttime_iso())
    with Timer("Full run"):
        set_cwd()
        main()
