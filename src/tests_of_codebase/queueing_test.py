#!/usr/bin/env python
import itertools

from cloud.clouds import get_region, Cloud, get_regions
from test_steps.do_test import do_batch
from util.utils import set_cwd, random_id, Timer, init_logger

init_logger()


def test1():
    run_id = random_id()
    t1 = (get_region(Cloud.GCP, "us-east1"), {})
    t2 = (get_region(Cloud.GCP, "us-central1"), {})
    t3 = (get_region(Cloud.AWS, "us-east-1"), {})
    t4 = (get_region(Cloud.AWS, "us-east-2"), {})

    test_input = [
        (t1, t2),
        (t2, t1),
        (t3, t4),
        (t4, t3),
    ]
    do_batch(run_id, test_input)


def test2():
    run_id = random_id()
    regions = get_regions()[:40]
    region_pairs = itertools.product(regions, regions)
    test_input = [((r[0], {}), (r[1], {})) for r in region_pairs]
    do_batch(run_id, test_input)


if __name__ == "__main__":
    with Timer("Full run"):
        set_cwd()
        test2()
