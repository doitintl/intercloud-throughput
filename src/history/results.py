import collections
import csv
import json
import logging
import os
import shutil
from typing import Optional

from cloud.clouds import CloudRegion
from util.utils import set_cwd

perftest_resultsdir_envvar = "PERFTEST_RESULTSDIR"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

results_dir = os.environ.get(perftest_resultsdir_envvar, "./results")
try:
    os.mkdir(results_dir)
except FileExistsError:
    pass

logging.info("Results dir is %s", results_dir)


def __results_dir_for_run(run_id):
    return f"./result-files-one-run/results-{run_id}"


def __results_file():
    return f"{results_dir}/results.csv"


def write_results_for_run(
    result_j, run_id: str, src_region_: CloudRegion, dst_region_: CloudRegion
):
    try:
        os.mkdir(__results_dir_for_run(run_id))
    except FileExistsError:
        pass
    results_for_one_run_file = (
        f"{__results_dir_for_run(run_id)}/results-{src_region_}-to-{dst_region_}.json"
    )
    # We write separate files for each test to avoid race conditions, since tests happen in parallel.
    with open(
        results_for_one_run_file,
        "w",
    ) as f:
        json.dump(result_j, f)
        logging.info("Wrote %s", results_for_one_run_file)


def load_past_results() -> list[dict]:
    def parse_nums(r) -> Optional[dict[str, float]]:
        ret = {}
        for k, v in r.items():
            if k in ["distance", "bitrate_Bps", "avgrtt"]:
                if not v:
                    return None
                try:
                    ret[k] = float(v)
                except ValueError as v:
                    logging.error(
                        "Parsing numbers; for key %s could not convert %s in %r",
                        k,
                        v,
                        r,
                    )
                    raise v
            else:
                ret[k] = v

        return ret

    try:

        with open(__results_file()) as f1:
            contents = f1.read()
            contents = contents.strip()
            if not contents:
                return []  # deal with empty file
        with open(__results_file()) as f:

            reader = csv.reader(f, skipinitialspace=True)
            header = next(reader)
            results = [dict(zip(header, row)) for row in reader]
            results = [parse_nums(r) for r in results]
            results = [r for r in results if r is not None]
            return results
    except FileNotFoundError:
        return []


def __count_tests_per_region_pair(
    ascending: bool, region_pairs: list[tuple[str, str, str, str]]
) -> list[dict[str, int]]:
    tests_per_regionpair = collections.Counter(region_pairs)
    items = tests_per_regionpair.items()
    multiplier = 1 if ascending else -1
    items = sorted(items, key=lambda i: multiplier * i[1])
    assert not items or len(items[0]) == 2 and type(items[0][1]) == int, items[0]

    # Here and elsewhere, timestamps  are at time of writing file,
    # so that the same testrun can get different timestamps. To allow identifying
    # a testrun, could use a timestamp from the begining of the run.
    # But run_id also gives that
    dicts = [
        {
            "count": count,
            "from_cloud": pair[0],
            "from_region": pair[1],
            "to_cloud": pair[2],
            "to_region": pair[3],
        }
        for pair, count in items
    ]
    return dicts


def analyze_test_count():
    def record_test_count(region_pairs: list[tuple[str, str, str, str]], filename: str):
        test_counts = __count_tests_per_region_pair(False, region_pairs)
        if not test_counts:
            logging.info(
                "No results found for %s. Either there are none, or you may need to check the %s env variable",
                filename,
                perftest_resultsdir_envvar,
            )
        else:
            with open(results_dir + "/" + filename, "w") as f:
                dict_writer = csv.DictWriter(f, test_counts[0].keys())
                dict_writer.writeheader()
                dict_writer.writerows(test_counts)

    dicts = load_past_results()
    if not dicts:
        logging.info(
            "No previous results found. You may need to check the   %s env variable",
            perftest_resultsdir_envvar,
        )
    else:
        by_test_pairs = [
            (d["from_cloud"], d["from_region"], d["to_cloud"], d["to_region"])
            for d in dicts
        ]

        record_test_count(by_test_pairs, "tests-per-regionpair.csv")


def combine_results(run_id: str):
    def json_to_flattened_dict(json_s: str) -> dict:
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

    if not os.path.exists(__results_dir_for_run(run_id)):
        logging.warning("No results at %s", __results_dir_for_run(run_id))
        return
    else:
        dicts = load_past_results()
        filenames = os.listdir(__results_dir_for_run(run_id))
        logging.info(
            f"Adding %d new results into %d existing results in %s",
            len(filenames),
            len(dicts),
            __results_file(),
        )
        if filenames:
            keys = None
            for fname in filenames:
                with open(f"{__results_dir_for_run(run_id)}/{fname}") as infile:
                    one_json = infile.read()
                    d = json_to_flattened_dict(one_json)
                    if not keys:
                        keys = list(d.keys())
                    else:
                        assert set(d.keys()) == set(
                            keys
                        ), f"All keys should be the same in the result-files-one-run jsons {set(d.keys())}!={set(keys)}"
                    dicts.append(d)

            with open(__results_file(), "w") as f:
                dict_writer = csv.DictWriter(f, keys)
                dict_writer.writeheader()
                dict_writer.writerows(dicts)

    shutil.rmtree(__results_dir_for_run(run_id))


if __name__ == "__main__":
    set_cwd()
    analyze_test_count()
