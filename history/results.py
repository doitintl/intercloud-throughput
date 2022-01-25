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
    logging.info(f"Combining {len(filenames)} results")
    with open(results_jsonl, "a") as outfile:
        for fname in filenames:
            with open(results_dir_for_this_runid + os.sep + fname) as infile:
                one_json = infile.read()
                outfile.write(one_json + "\n")
