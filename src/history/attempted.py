import csv
import logging
import os.path

from cloud.clouds import CloudRegion, get_region
from history.results import load_past_results, results_dir
from util.utils import date_s


def __attempted_tests_csv_file():
    return f"{results_dir}/attempted-tests.csv"


def without_already_succeeded(
    region_pairs: list[tuple[CloudRegion, CloudRegion]]
) -> list[tuple[CloudRegion, CloudRegion]]:
    successful_results = __results_dict_to_cloudregion_pairs_with_dedup(
        load_past_results()
    )
    already_attempted = __results_dict_to_cloudregion_pairs_with_dedup(
        __already_attempted()
    )
    old_failures = [p for p in already_attempted if p not in successful_results]

    no_redo_success = list(filter(lambda r: r not in successful_results, region_pairs))
    logging.info(
        f"Of {len(region_pairs)} requested in this batch; "
        f"Excluding the {len(successful_results)} successes; "
        f"Not excluding the {len(old_failures)} failures; "
        f"Leaving {len(no_redo_success)} pairs."
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


def write_missing_regions(*missing_regions: list[CloudRegion]):
    output_filename = f"{results_dir}/failed-to-create-vm.csv"
    write_hdr = not os.path.exists(output_filename)

    with open(output_filename, "a") as f:
        if write_hdr:
            f.write(",".join(["timestamp", "cloud", "region"]) + "\n")
        r: CloudRegion
        for r in missing_regions:
            entry = f"{date_s()},{r.cloud},{r.region_id}\n"
            f.write(entry)


def write_failed_test(src: CloudRegion, dst: CloudRegion):
    output_filename = f"{results_dir}/failed-tests.csv"
    write_hdr = not os.path.exists(output_filename)

    entry = f"{date_s()},{src.cloud},{src.region_id}," f"{dst.cloud},{dst.region_id}\n"

    with open(output_filename, "a") as f:
        if write_hdr:
            f.write(
                ",".join(
                    ["timestamp", "from_cloud", "from_region", "to_cloud", "to_region"]
                )
                + "\n"
            )
        f.write(entry)


def write_attempted_tests(
    region_pairs_about_to_try: list[tuple[CloudRegion, CloudRegion]]
):
    attempts = __already_attempted()
    for pair in region_pairs_about_to_try:
        attempts.append(
            {
                "timestamp": date_s(),
                "from_cloud": pair[0].cloud,
                "from_region": pair[0].region_id,
                "to_cloud": pair[1].cloud,
                "to_region": pair[1].region_id,
            }
        )

    if attempts:
        keys = list(attempts[0].keys())
        with open(__attempted_tests_csv_file(), "w") as f:
            dict_writer = csv.DictWriter(f, keys)
            dict_writer.writeheader()
            dict_writer.writerows(attempts)


def __already_attempted() -> list[dict]:
    try:
        with open(__attempted_tests_csv_file()) as f:
            reader = csv.reader(f, skipinitialspace=True)
            header = next(reader)
            attempts = [dict(zip(header, row)) for row in reader]
            return attempts
    except FileNotFoundError:
        return []
