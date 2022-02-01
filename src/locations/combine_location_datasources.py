import csv
import itertools
import os
from statistics import median, mean, stdev, variance
from typing import List, Dict

from util.utils import set_cwd


def __combine():
    groups = data_by_region()
    geoloc = {}
    for region_name, data in groups.items():

        lats = [float(d["latitude"]) for d in data]

        longs = [float(d["longitude"]) for d in data]
        stat_lat = stats("lat", lats)
        stat_long = stats("long", longs)
        sources = "/".join(d["source"] for d in data)
        geoloc_data = {
            "source": sources,
            "cloud": region_name[0],
            "region": region_name[1],
            "count": len(data),
        }

        geoloc_data |= stat_lat
        for d in data:
            geoloc_data[d["source"] + "_lat"] = d["latitude"]

        geoloc_data |= stat_long
        for d in data:
            geoloc_data[d["source"] + "_long"] = d["longitude"]
        geoloc_data["latitude"] = geoloc_data["lat_median"]
        geoloc_data["longitude"] = geoloc_data["long_median"]
        geoloc[region_name] = geoloc_data

    geoloc_list = list(filter(lambda g: g["cloud"] in ["AWS", "GCP"], geoloc.values()))

    keys = [
        "cloud",
        "region",
        "latitude",
        "longitude",
        "count",
        "lat_mean",
        "lat_median",
        "lat_stdev",
        "lat_variance",
        "sunshower_lat",
        "MaestroPanel_lat",
        "cockroach_lat",
        "geoloc_lat",
        "datacenters.com_lat",
        "jsonmaur_lat",
        "yugabyte_lat",
        "long_mean",
        "long_median",
        "long_stdev",
        "long_variance",
        "sunshower_long",
        "MaestroPanel_long",
        "cockroach_long",
        "geoloc_long",
        "datacenters.com_long",
        "jsonmaur_long",
        "yugabyte_long",
        "source",
    ]

    with open("./reference_data/locations.csv", "w") as f:
        dict_writer = csv.DictWriter(f, keys)
        dict_writer.writeheader()
        dict_writer.writerows(geoloc_list)


def stats(pfx: str, vals: List[float]) -> Dict[str, float]:
    def variance_(lst):
        return 0 if len(lst) < 2 else variance(lst)

    def stdev_(lst):
        return 0 if len(lst) < 2 else stdev(lst)

    pfx += "_"
    d = {
        f"{pfx}mean": mean(vals),
        f"{pfx}median": median(vals),
        f"{pfx}stdev": stdev_(vals),
        f"{pfx}variance": variance_(vals),
    }
    return {k: round(v, 2) for k, v in d.items()}


def data_by_region() -> Dict[tuple[str, str], List[Dict]]:
    def load_csv(fname):
        with open(fname) as f:
            return [r for r in (csv.DictReader(filter(lambda row: row[0] != "#", f)))]

    dir_ = "./reference_data/data_sources/"
    lst = os.listdir(dir_)
    dicts = [load_csv(dir_ + f) for f in lst]
    dicts = list(itertools.chain.from_iterable(dicts))

    def keyfunc(d):
        if not d.get("cloud") or not d.get("region"):
            raise ValueError(f"{d}")
        return d["cloud"], d["region"]

    dicts = sorted(dicts, key=keyfunc)
    grouped_ = itertools.groupby(dicts, keyfunc)
    groups = {}
    for k, g in grouped_:
        groups[k] = list(g)  # Store group iterator as a list
        pass
    return groups


def main():
    set_cwd()
    # geoloc.preprocess()
    # sunshower.preprocess()
    # yugabyte.preprocess()
    set_cwd()
    __combine()


if __name__ == "__main__":
    main()
