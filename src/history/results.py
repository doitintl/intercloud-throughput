import collections
import csv

import json
import logging
import os

from typing import List, Dict, Tuple

from util.utils import set_cwd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

results_dir = os.environ.get("PERFTEST_RESULTSDIR", "./results")
logging.info("Results dir is %s", results_dir)

__results_csv = f"{results_dir}/results.csv"


def load_results_csv() -> List[Dict]:
    def parse_nums(r):
        ret = {}
        for k, v in r.items():
            if k in ["distance", "bitrate_Bps", "avgrtt"]:
                try:
                    ret[k] = float(v)
                except ValueError as v:
                    logging.error(
                        "Parsing numbers; for key  %s could not convert %s in %r",
                        k,
                        v,
                        r,
                    )
                    raise v
            else:
                # TODO could convert datetime ; could convert from_cloud to Cloud obj and
                # Cloud/region strs to CLoudRegion obj
                ret[k] = v

        return ret

    try:
        with open(__results_csv) as f:
            reader = csv.reader(f, skipinitialspace=True)
            header = next(reader)
            results = [dict(zip(header, row)) for row in reader]
            results = [parse_nums(r) for r in results]
            return results
    except FileNotFoundError:
        return []


def record_supernumerary_tests():
    def record_test_count(
        title, hdrs, region_pairs: List[Tuple[str, str, str, str]], id: str
    ):
        tests_per_regionpair = collections.Counter(region_pairs)
        regionpair_items = sorted(
            list(tests_per_regionpair.items()), key=lambda i: -i[1]
        )
        regionpair_strings = [
            f"{v},{k[0]},{k[1]},{k[2]},{k[3]}" for k, v in regionpair_items
        ]
        s = "\n".join(regionpair_strings)
        logging.info("%s %s", id, s)
        with open(results_dir + "/" + f"{id}.csv", "w") as f:
            f.write("#" + title + "\n")
            f.write(",".join(hdrs) + "\n")
            f.write(s)

    dicts = load_results_csv()
    if not dicts:
        raise ValueError
    by_test_pairs = [
        (d["from_cloud"], d["from_region"], d["to_cloud"], d["to_region"])
        for d in dicts
    ]
    hdr = ["count", "from_cloud", "from_region", "to_cloud", "to_region"]
    record_test_count(
        "Tests per Region Pair", hdr, by_test_pairs, "tests_per_regionpair"
    )
    intraregion_tests = list(
        filter(lambda i: (i[0], i[1]) == (i[2], i[3]), by_test_pairs)
    )
    record_test_count("Intraregion tests", hdr, intraregion_tests, "intraregion_tests")


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
    record_supernumerary_tests()

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


if __name__ == "__main__":
    set_cwd()
    record_supernumerary_tests()
