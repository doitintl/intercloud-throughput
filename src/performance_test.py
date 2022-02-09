#!/usr/bin/env python
import logging

from graph.plot_chart import graph_full_testing_history
from test_steps import batching
from util.utils import set_cwd, random_id, Timer, date_s

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)




def main():
    logging.info("Started at %s", date_s())
    batches = batching.setup_batches()

    run_id = random_id()
    logging.info("Run ID is %s", run_id)

    for batch in batches:
        batching.batch_setup_test_teardown(batch, run_id)

    graph_full_testing_history()


if __name__ == "__main__":
    with Timer("Full run"):
        set_cwd()
        main()
