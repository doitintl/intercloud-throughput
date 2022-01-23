import csv
import itertools
import json
import logging
import os
from functools import reduce
from typing import List, Tuple, Dict

import cloud
from cloud import clouds
from cloud.clouds import CloudRegion, get_cloud_region

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

__results_csv = "./data/results.csv"

results_jsonl = "./data/results.jsonl"


def untested_regionpairs() -> List[Tuple[CloudRegion, CloudRegion]]:
    test_results_: List[Dict]
    test_results_ = __load_results_json()

    def region_from_dict(dict_, pfx):
        return get_cloud_region(
            cloud.clouds.Cloud(dict_[f"{pfx}_cloud"]), dict_[f"{pfx}_region"]
        )

    all_regions: List[CloudRegion]
    all_regions = cloud.clouds.get_regions()
    all_pairs_with_dup = itertools.product(all_regions, all_regions)
    all_pairs = [p for p in all_pairs_with_dup if p[0] != p[1]]
    tested_pairs = []
    for result in test_results_:
        from_cloud = region_from_dict(result, "from")
        to_cloud = region_from_dict(result, "to")
        tested_pairs.append((from_cloud, to_cloud))
    untested = [p for p in all_pairs if p not in tested_pairs]
    return untested


def load_results_csv() -> List[Dict]:
    with open(__results_csv) as f:
        reader = csv.reader(f, skipinitialspace=True)
        header = next(reader)
        results = [dict(zip(header, row)) for row in reader]
        return results


def __load_results_json() -> List[Dict]:
    def test_key(d):
        return d["from_cloud"], d["from_region"], d["to_cloud"], d["to_region"]

    test_keys = []
    dups=[]
    def load_jsonl_and_convert():
        dicts = []
        with open(results_jsonl) as f:
            for jsonl in f:
                d = {}

                j = json.loads(jsonl)
                for k, v in j.items():
                    if isinstance(v, dict):
                        for k2, v2 in v.items():
                            assert isinstance(v2, (str, int, float, bool))
                            d[f"{k}_{k2}"] = v2
                    else:
                        d[k] = v
                test_key_ = test_key(d)
                if test_key_ not in test_keys:
                    dicts.append(d)
                    test_keys.append(test_key_)
                else:
                    dups.append(test_key_)
        logging.info("%d duplicates %s", len(dups), dups)
        return dicts


    test_results_: List[Dict]
    test_results_ = load_jsonl_and_convert()
    test_results_.sort(key=test_key)
    return test_results_


def jsonl_to_csv():
    def write(dicts):
        keys = reduce(lambda x, y: x + y, [list(d.keys()) for d in dicts])
        with open(__results_csv, "w") as f:
            dict_writer = csv.DictWriter(f, keys)
            dict_writer.writeheader()
            dict_writer.writerows(dicts)

    test_results_ = __load_results_json()
    write(test_results_)
    logging.info("Wrote results.csv")


if __name__ == "__main__":
    jsonl_to_csv()


def combine_results_to_jsonl(results_dir_for_this_runid):
    filenames = os.listdir(results_dir_for_this_runid)
    with open(results_jsonl, "a") as outfile:
        for fname in filenames:
            with open(results_dir_for_this_runid + os.sep + fname) as infile:
                one_json = infile.read()
                outfile.write(one_json + "\n")
