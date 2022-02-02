import csv
import json

import requests as requests

from util.utils import set_cwd


def preprocess():
    url = "https://raw.githubusercontent.com/sunshower-io/provider-lists/master/aws/output/regions.json"

    r = requests.get(url, allow_redirects=True)

    rows = []
    json_s = r.content

    keys = None
    data = json.loads(json_s)
    regions = data["regions"]
    for region in regions:
        row = {
            "source": "sunshower",
            "cloud": "AWS",
            "region": region["key"],
            "latitude": region["coordinates"]["latitude"],
            "longitude": region["coordinates"]["longitude"],
        }
        assert not keys or keys == list(row.keys())
        keys = list(row.keys())
        rows.append(row)

    with open("./reference_data/data_sources/sunshower-aws-loc.csv", "w") as f:
        dict_writer = csv.DictWriter(f, keys)
        dict_writer.writeheader()
        dict_writer.writerows(rows)


if __name__ == "__main__":
    set_cwd()
    preprocess()
