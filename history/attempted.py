import csv
import logging
from typing import List, Tuple, Dict


from cloud.clouds import CloudRegion, get_cloud_region, Cloud
from history.results import load_results_csv, data_dir


__attempted_tests_csv = f"{data_dir}/attempted-tests.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def without_already_attempted(
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
        f"Will not redo the {len(successful_results)} successes; "
        f"WILL retry the {len(old_failures)} failures; "
        f"Testing {len(no_redo_success)} pairs."
    )
    return no_redo_success


def __results_dict_to_cloudregion_pairs_with_dedup(dicts):
    return set(
        [
            (
                get_cloud_region(Cloud(d["from_cloud"]), d["from_region"]),
                get_cloud_region(Cloud(d["to_cloud"]), d["to_region"]),
            )
            for d in dicts
        ]
    )


def write_attempted_tests(region_pairs):
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
    with open(__attempted_tests_csv, "w") as f:
        dict_writer = csv.DictWriter(
            f, ["from_cloud", "from_region", "to_cloud", "to_region"]
        )
        dict_writer.writeheader()
        dict_writer.writerows(attempts)


def __already_attempted() -> List[Dict]:
    try:
        with open(__attempted_tests_csv) as f:
            reader = csv.reader(f, skipinitialspace=True)
            header = next(reader)
            attempts = [dict(zip(header, row)) for row in reader]
            return attempts
    except FileNotFoundError:
        return []
