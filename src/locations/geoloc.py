import csv
import json

from util.utils import set_cwd


def in_already(row, rows):
    return row["region"] in [r["region"] for r in rows]


def preprocess():
    with open("./reference_data/raw_data/aws-regions-geoloc.json") as f1:
        rows = []
        json_s = f1.read()

        keys = None
        data = json.loads(json_s)
        regions = data["regions"]
        for region in regions:
            az_ = region["az"][
                  :-1
                  ]  # all AZs of a given region in this list have the same lat/long
            row = {
                "source": "geoloc",
                "cloud": "AWS",
                "region": az_,
                "latitude": region["latitude"],
                "longitude": region["longitude"],
            }
            assert not keys or keys == list(row.keys())
            keys = list(row.keys())
            if not in_already(row, rows):
                rows.append(row)

        rows.sort(key=lambda r: r["region"])
        with open("./reference_data/data_sources/aws-geoloc.csv", "w") as f2:
            dict_writer = csv.DictWriter(f2, keys)
            dict_writer.writeheader()
            dict_writer.writerows(rows)


if __name__ == "__main__":
    set_cwd()
    preprocess()
