import csv
import logging
from typing import List, Tuple, Dict


from cloud.clouds import CloudRegion, get_cloud_region, Cloud
from history.results import load_results_csv
from util.utils import dedup

__attempted_tests_csv = "./data/attempted_tests.csv"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def remove_already_attempted(
    region_pairs: List[Tuple[CloudRegion, CloudRegion]]
) -> List[Tuple[CloudRegion, CloudRegion]]:
    already_attempted = __results_dict_to_cloudregion_pairs_with_dedup(__already_attempted())
    successful_results = __results_dict_to_cloudregion_pairs_with_dedup(load_results_csv())

    old_failures = [p for p in already_attempted if p not in successful_results]

    ret = list(filter(lambda r: r not in already_attempted, region_pairs))

    print(
        f"Of {len(region_pairs)} to be tested; "
        f"Will not do any of the {len(successful_results)} successful ; "
        f"Or {len(old_failures)}   failures; "
        f"Testing {len(ret)} pairs"
    )
    return ret


def __results_dict_to_cloudregion_pairs_with_dedup(dicts):
    return dedup( [
        (
            get_cloud_region(Cloud(d["from_cloud"]), d["from_region"]),
            get_cloud_region(Cloud(d["to_cloud"]), d["to_region"]),
        )
        for d in dicts
    ])


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
