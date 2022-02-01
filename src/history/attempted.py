import csv
import logging
import os.path
from datetime import datetime
from typing import List, Tuple, Dict

from cloud.clouds import CloudRegion, get_region
from history.results import load_results_csv, results_dir


def __attempted_tests_csv_file():
    return f"{results_dir}/attempted-tests.csv"


def __failed_tests_csv_file():
    return f"{results_dir}/failed-tests.csv"


def without_already_succeeded(
        region_pairs: List[Tuple[CloudRegion, CloudRegion]]
) -> List[Tuple[CloudRegion, CloudRegion]]:
    successful_results = __results_dict_to_cloudregion_pairs_with_dedup(
        load_results_csv()
    )
    already_attempted = __results_dict_to_cloudregion_pairs_with_dedup(
        __already_attempted()
    )
    old_failures = [p for p in already_attempted if p not in successful_results]

    no_redo_success = list(filter(lambda r: r not in successful_results, region_pairs))
    # no_redo_any_attempted = list(
    #    filter(lambda r: r not in already_attempted, region_pairs)
    # )
    print(
        f"Of {len(region_pairs)} to be tested; "
        f"Excluding the {len(successful_results)} successes; "
        f"Not excluding the {len(old_failures)} failures; "
        f"Testing {len(no_redo_success)} pairs."
    )
    return no_redo_success


def __results_dict_to_cloudregion_pairs_with_dedup(dicts):
    return set(
        [
            (
                get_region(d["from_cloud"], d["from_region"]),
                get_region(d["to_cloud"], d["to_region"]),
            )
            for d in dicts
        ]
    )


def write_failed_test(p: Tuple[CloudRegion, CloudRegion]):
    write_hdr = not os.path.exists(__failed_tests_csv_file())

    entry = (
        f"{datetime.now().isoformat()},{p[0].cloud},{p[0].region_id},"
        f"{p[1].cloud},{p[1].region_id}\n"
    )

    with open(__failed_tests_csv_file(), "a") as f:
        if write_hdr:
            f.write(
                ",".join(
                    ["timestamp", "from_cloud", "from_region", "to_cloud", "to_region"]
                )
                + "\n"
            )
        f.write(entry)
        logging.info("Wrote to %s", __failed_tests_csv_file())


def write_attempted_tests(region_pairs: List[Tuple[CloudRegion, CloudRegion]]):
    attempts = __already_attempted()
    for pair in region_pairs:
        attempts.append(
            {
                "from_cloud": pair[0].cloud,
                "from_region": pair[0].region_id,
                "to_cloud": pair[1].cloud,
                "to_region": pair[1].region_id,
            }
        )
    with open(__attempted_tests_csv_file(), "w") as f:
        dict_writer = csv.DictWriter(
            f, ["from_cloud", "from_region", "to_cloud", "to_region"]
        )
        dict_writer.writeheader()
        dict_writer.writerows(attempts)


def __already_attempted() -> List[Dict]:
    try:
        with open(__attempted_tests_csv_file()) as f:
            reader = csv.reader(f, skipinitialspace=True)
            header = next(reader)
            attempts = [dict(zip(header, row)) for row in reader]
            return attempts
    except FileNotFoundError:
        return []
