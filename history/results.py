import collections
import csv

import json
import logging
import os

from typing import List, Dict

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
data_dir = "./data"

__results_csv = f"{data_dir}/results.csv"


def load_results_csv() -> List[Dict]:
    try:
        with open(__results_csv) as f:
            reader = csv.reader(f, skipinitialspace=True)
            header = next(reader)
            results = [dict(zip(header, row)) for row in reader]
            return results
    except FileNotFoundError:
        return []


def __log_supernumerary_tests(dicts):
    by_test_pairs=[(d["from_cloud"],d[ "from_region"],d[ "to_cloud"],d[ "to_region"]) for d in dicts]
    c=collections.Counter(by_test_pairs)
    items=sorted(list(c.items()), key=lambda i: -i[1])

    def region_s(q):
        return f"{q[0]} {q[1]} to {q[2]} {q[3]}"

    items_s=[f"{v}: {region_s(k)}" for k,v in items]
    s="\n".join(items_s)

    logging.info("Frequency of test for each pair\n%s",s)
    same_region_tests=[i for i  in by_test_pairs if (i[0], i[1])==(i[2], i[3])]
    logging.info("Same-region tests\n%s","\n".join(set(sorted([region_s(p) for p in same_region_tests]))))




def combine_results_to_csv(results_dir_for_this_runid):
    def json_to_flattened_dict(json_s: str) -> Dict:
        ret = {}
        j = json.loads(json_s)
        for k, v in j.items():
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    assert isinstance(v2, (str, int, float, bool))
                    ret[f"{k}_{k2}"] = v2
            else:
                ret[k] = v
        return ret

    filenames = os.listdir(results_dir_for_this_runid)
    dicts = load_results_csv()
    __log_supernumerary_tests(dicts)
    logging.info(
        f"Adding %d new results into %d existing results in %s",
        len(filenames),
        len(dicts),
        __results_csv,
    )

    keys = None
    for fname in filenames:
        with open(f"{results_dir_for_this_runid}/{fname}") as infile:
            one_json = infile.read()
            d = json_to_flattened_dict(one_json)
            if not keys:
                keys = list(d.keys())
            else:
                assert set(d.keys()) == set(
                    keys
                ), f"All keys should be the same in the result-files-one-run jsons {set(d.keys())}!={set(keys)}"
            dicts.append(d)

    with open(__results_csv, "w") as f:
        dict_writer = csv.DictWriter(f, keys)
        dict_writer.writeheader()
        dict_writer.writerows(dicts)

if __name__=="__main__":

    dicts = load_results_csv()
    __log_supernumerary_tests(dicts)