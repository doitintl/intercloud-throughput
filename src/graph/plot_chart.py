import logging
import os
import subprocess
from datetime import datetime
from math import log2
from os import mkdir
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import pyplot
from matplotlib.axes import Axes
from numpy.linalg import LinAlgError
from scipy.stats import pearsonr

from cloud.clouds import interregion_distance, get_region, Cloud
from history.results import load_past_results, results_dir, perftest_resultsdir_envvar
from util.utils import set_cwd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

mega = 1e6


def graph_full_testing_history():
    results = load_past_results()
    if not results:
        raise ValueError(
            "No results in %s; maybe set another value for %s env variable"
            % (results_dir, perftest_resultsdir_envvar)
        )
    len_intra_and_interzone = len(results)
    # Eliminate intra-zone tests
    results = list(
        filter(
            lambda d: (
                (d["from_cloud"], d["from_region"]) != (d["to_cloud"], d["to_region"])
            ),
            results,
        )
    )
    if not results:
        raise ValueError("No inter-zone results available")

    if len(results) < len_intra_and_interzone:
        logging.info(
            "Removed %d intrazone results", len(results) < len_intra_and_interzone
        )

    for result in results:
        result["distance"] = interregion_distance(
            get_region((result["from_cloud"]), result["from_region"]),
            get_region((result["to_cloud"]), result["to_region"]),
        )

    results.sort(key=lambda d: d["distance"])

    clouddata: dict[Optional[tuple[Cloud, Cloud]], dict[str, list]] = {}
    clouddata[None] = __statistics(results)
    s = ""
    for from_cloud in Cloud:
        for to_cloud in Cloud:
            cloudpair_results = [
                r
                for r in results
                if (from_cloud.name, to_cloud.name) == (r["from_cloud"], r["to_cloud"])
            ]
            s += "\t%s,%s has %d results\n" % (
                from_cloud,
                to_cloud,
                len(cloudpair_results),
            )

            clouddata[(from_cloud, to_cloud)] = __statistics(cloudpair_results)
    logging.info("Test distribution:\n" + s)
    __plot(clouddata)


def __statistics(results):
    def extract(key):
        return [r[key] for r in results]

    return {
        "distance": extract("distance"),
        "bitrate_Bps": [r / mega for r in extract("bitrate_Bps")],
        "avgrtt": extract("avgrtt"),
    }


def __plot(clouddata: dict[Optional[tuple[Cloud, Cloud]], dict[str, list]]):

    datetime_s = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    subdir = os.path.abspath(f"{results_dir}/charts/{datetime_s}")
    logging.info("Generating charts in %s", subdir)

    Path(subdir).mkdir(parents=True, exist_ok=True)

    for i, (cloudpair, data) in enumerate(clouddata.items()):
        __plot_figure(i, cloudpair, clouddata, subdir)
    import platform

    if platform.system() == "Darwin":
        subprocess.call(["open", subdir])


def __plot_figure(count, cloudpair, clouddata, subdir):
    dist: list[float] = clouddata[cloudpair]["distance"]
    avg_rtt: list[float] = clouddata[cloudpair]["avgrtt"]
    bitrate: list[float] = clouddata[cloudpair]["bitrate_Bps"]
    if not dist:  # No data
        return

    plt.figure(count)
    fig, base_ax = plt.subplots()
    rtt_ax = base_ax
    bitrate_ax = base_ax.twinx()

    plt.xlabel = "distance"

    __plot_series(
        cloudpair,
        f"avg rtt",
        dist,
        avg_rtt,
        rtt_ax,
        "upper left",
        "red",
        unit="seconds",
        bottom=0,
        top=300,
        semilogy=False,
    )
    __plot_series(
        cloudpair,
        f"bitrate",
        dist,
        bitrate,
        bitrate_ax,
        "upper right",
        color="blue",
        unit="Mbps",
        bottom=1,
        top=3000,
        semilogy=True,

    )
    plt.title(f"{__cloudpair_s(cloudpair)}: Distance to latency & throughput")
    chart_file = f"{subdir}/{__cloudpair_s(cloudpair)}.png"
    try:
        mkdir(os.path.dirname(os.path.realpath(chart_file)))
    except FileExistsError:
        pass
    pyplot.savefig(chart_file)

    plt.show()


def __cloudpair_s(cloudpair):
    return "All Data" if cloudpair is None else f"{cloudpair[0]}-{cloudpair[1]}"


def __plot_series(
    cloudpair: tuple[Cloud, Cloud],
    series_name: str,
    x: list,
    y: list,
    axis,
    loc: str,
    color: str,
    unit: str,
    bottom: int,
    top: int,
    semilogy: bool,
):

    if semilogy:
        axis.set_yscale("log")
        ylabel = f"{unit} (log)"
        corr, _ = pearsonr(x, [log2(i) for i in y])
    else:
        ylabel = unit
        corr, _ = pearsonr(x, y)

    axis.set_ylabel(ylabel)

    plt.xlim(
        0, 17000
    )  # 20000 km is  half the circumf of earth, and the farthest pairs of data centers are 18000km
    axis.set_ylim(bottom, top)

    axis.scatter(
        x,
        y,
        color=color,
        label=f"{series_name}\n(r={round(corr, 2)})",
    )
    axis.legend(loc=loc)

    #__plot_linear_fit(axis, x, y, color, lbl=series_name, semilogy=semilogy)




LinAlgError_counter = 0


def __plot_linear_fit(ax: Axes, dist, y, color, lbl=None, semilogy=False):
    dist_np = np.array(dist)
    y_np = np.array(y)
    try:

        # noinspection PyTupleAssignmentBalance
        returned = np.polyfit(dist_np, y_np, 1, full=True)
        m, b = returned[0]

        logging.info("For %s, slope is %f and intercept is %f", lbl, m, b)
        if semilogy:
            plot_func = ax.semilogy
        else:
            plot_func = ax.plot
        plot_func(
            dist_np,
            m * dist_np + b,
            color=color,
            linestyle="dashed",
            label=lbl,
        )
    except LinAlgError as lae:
        global LinAlgError_counter
        LinAlgError_counter += 1
        logging.warning("%s: %s and %s", lae, dist_np[:10], y_np[:10])
        ax.text(
            2000,
            3500 - (LinAlgError_counter * 500),
            f"No linear fit to {lbl} available",
            fontsize=10,
            style="italic",
            bbox={"facecolor": "red", "alpha": 0.5, "pad": 3},
        )


if __name__ == "__main__":
    set_cwd()
    graph_full_testing_history()
