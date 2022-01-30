# yugabyte
# Copyright (c) YugaByte, Inc.
# Apache 2.0 License https://github.com/yugabyte/yugabyte-db/blob/master/licenses/APACHE-LICENSE-2.0.txt
import csv
import yaml
from util.utils import set_cwd
import requests as requests


def preprocess():
    url = "https://raw.githubusercontent.com/yugabyte/yugabyte-db/master/managed/src/main/resources/configs/gcp-region-metadata.yml"

    r = requests.get(url, allow_redirects=True)

    rows = []
    full_yaml = r.content

    keys = None
    try:
        data = yaml.safe_load(full_yaml)
        for region_name, v in data.items():
            row = {
                "source": "yugabyte",
                "cloud": "GCP",
                "region": region_name,
                "latitude": v["latitude"],
                "longitude": v["longitude"],
            }
            assert not keys or keys == list(row.keys())
            keys = list(row.keys())
            rows.append(row)
    except yaml.YAMLError as exc:
        print(exc)

    with open("./reference_data/data_sources/yugabyte-gcp-loc.csv", "w") as f:
        dict_writer = csv.DictWriter(f, keys)
        dict_writer.writeheader()
        dict_writer.writerows(rows)


if __name__ == "__main__":
    set_cwd()
    preprocess()
