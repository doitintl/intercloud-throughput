import itertools
import logging
import os
import platform
import subprocess
from datetime import datetime
from math import log10
from os import mkdir
from pathlib import Path
from statistics import mean
from typing import Optional, Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import pyplot
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from numpy.linalg import LinAlgError
from scipy.stats import pearsonr

from cloud.clouds import interregion_distance, get_region, Cloud
from history.results import load_history, results_dir, perftest_resultsdir_envvar
from util.utils import set_cwd


def __statistics(results):
    def extract(key):
        return [r[key] for r in results]

    mega = 1e6

    return {
        "distance": extract("distance"),
        "bitrate_Bps": [r / mega for r in extract("bitrate_Bps")],
        "avgrtt": extract("avgrtt"),
    }


def graph_full_testing_history():
    clouddata = __prepare_data()
    __log_mean_ratios(clouddata)

    __plot_figures(clouddata)


def __log_mean_ratios(clouddata):
    bitrate_multiplier = 10000
    avgrtt_s = f"Mean of {bitrate_multiplier} log(bitrate)/dist\n"
    bitrate_s = "Mean of avg RTT/dist\n"
    for cloudpair, data in clouddata.items():
        dist = data["distance"]
        if not dist:
            continue
        bitrate = data["bitrate_Bps"]
        avg_rtt = data["avgrtt"]
        assert len(dist) == len(bitrate) == len(avg_rtt)
        mean_bitrate = mean(
            [log10(bitrate[i]) / dist[i] for i in range(len(dist)) if dist[i] != 0]
        )

        bitrate_s += "\t%s: %s\n" % (
            __cloudpair_s(cloudpair),
            round(bitrate_multiplier * mean_bitrate, 1),
        )

        mean_avgrtt = mean(
            [avg_rtt[j] / dist[j] for j in range(len(dist)) if dist[j] != 0]
        )
        avgrtt_s += "\t%s: %s\n" % (__cloudpair_s(cloudpair), round(1 / mean_avgrtt, 1))
    logging.info("\n" + bitrate_s + "\n" + avgrtt_s)


def __prepare_data():
    results = load_history()
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
    clouddata: dict[Optional[tuple[Cloud, Cloud]], dict[str, list]] = {
        None: __statistics(results)
    }
    s = ""
    cross_prod = list(itertools.product(Cloud, Cloud))
    def homogeneous_first(p:tuple[Cloud,Cloud] ):
        return -1 * int(__homogeneous(p)), str(p)

    cross_prod.sort(key=homogeneous_first)
    for (from_cloud, to_cloud) in cross_prod:
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
    return clouddata


def __plot_figures(
    data_by_cloudpair: dict[Optional[tuple[Cloud, Cloud]], dict[str, list]]
):
    datetime_s = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    subdir = os.path.abspath(f"{results_dir}/charts/{datetime_s}")
    logging.info("Generating charts in %s", subdir)

    Path(subdir).mkdir(parents=True, exist_ok=True)

    for i, (cloudpair, data) in enumerate(data_by_cloudpair.items()):
        if cloudpair is None:
            # TODO The multiplot adds complexity as it sets up multiple code paths down the stack.
            __plot_figure(i, None, data_by_cloudpair, subdir, multiplot=True)
        else:
            __plot_figure(i, cloudpair, data_by_cloudpair, subdir, multiplot=False)

    if platform.system() == "Darwin":
        subprocess.call(["open", subdir])


def __plot_figure(
    count: int,
    cloudpair: Optional[tuple[Cloud, Cloud]],
    clouddata: dict[Optional[tuple[Cloud, Cloud]]],
    subdir: str,
    multiplot: bool,
):

    dist, avg_rtt, bitrate = [
        clouddata[cloudpair][k] for k in ["distance", "avgrtt", "bitrate_Bps"]
    ]

    if not dist:  # No data
        return

    plt.figure(count)
    fig, base_ax = plt.subplots()
    avg_rtt_ax = base_ax
    bitrate_ax = base_ax.twinx()

    plt.xlabel = "distance"

    if not multiplot:
        _, _ = __plot_both_series(
            cloudpair, dist, avg_rtt, bitrate, avg_rtt_ax, bitrate_ax, multiplot
        )
    else:
        __multiplot_figure(avg_rtt_ax, bitrate_ax, clouddata, cloudpair, multiplot)

    plt.title(f"{__cloudpair_s(cloudpair)}: Distance to latency & throughput")

    chart_file = f"{subdir}/{__cloudpair_s(cloudpair)}{' by cloud pair' if multiplot else ''}.png"
    try:
        mkdir(os.path.dirname(os.path.realpath(chart_file)))
    except FileExistsError:
        pass
    pyplot.savefig(chart_file)

    plt.show()

def __homogeneous(p:tuple[Any, Any]):
    return p[0] == p[1]

def __cloudpair_s(pair: tuple[Cloud, Cloud]) -> str:
    if pair is None:
        return "All Data"
    else:
        return f"{pair[0].name} to {pair[1].name}"


def __multiplot_figure(avg_rtt_ax, bitrate_ax, clouddata, _cloudpair_None, multiplot):
    avg_rtt_legend_loc = "lower right"
    bitrate_legend_loc = "lower center"

    center_horiz = 0.46
    center_vert = 0.29
    right = 0.82
    bitrate_legend_tag_vertical = center_vert
    bitrate_legend_tag_horiz = center_horiz
    avg_rtt_legend_tag_vertical = center_vert
    avg_rtt_legend_tag_horiz = right

    avg_rtt_lines = []
    bitrate_lines = []
    labels = []
    assert not _cloudpair_None  # "None" value indicates all data
    # Don't plot the aggregated values in this disaggregated chart
    clouddata = {k: v for k, v in clouddata.items() if k}  #

    for j, (cloudpair_, cpair_data) in enumerate(clouddata.items()):

        dist, avg_rtt, bitrate = [
            clouddata[cloudpair_][k] for k in ["distance", "avgrtt", "bitrate_Bps"]
        ]
        if not dist:
            continue
        avg_rtt_line, bitrate_line = __plot_both_series(
            cloudpair_, dist, avg_rtt, bitrate, avg_rtt_ax, bitrate_ax, multiplot
        )
        labels.append(__cloudpair_s(cloudpair_))
        avg_rtt_lines.append(avg_rtt_line)
        bitrate_lines.append(bitrate_line)

        avg_rtt_ax.legend(avg_rtt_lines, labels, loc=avg_rtt_legend_loc)
        bitrate_ax.legend(bitrate_lines, labels, loc=bitrate_legend_loc)

        avg_rtt_ax.text(
            avg_rtt_legend_tag_horiz,
            avg_rtt_legend_tag_vertical,
            "avg RTT",
            transform=avg_rtt_ax.transAxes,
            fontsize=10,
        )

        bitrate_ax.text(
            bitrate_legend_tag_horiz,
            bitrate_legend_tag_vertical,
            "bitrate",
            transform=bitrate_ax.transAxes,
            fontsize=10,
        )


def __plot_both_series(
    cloudpair: tuple[Cloud, Cloud],
    dist: list,
    avg_rtt: list,
    bitrate: list,
    rtt_ax,
    bitrate_ax,
    multiplot: bool,
) -> tuple[PathCollection, PathCollection]:

    bitrate_colors = {
        (Cloud.GCP, Cloud.GCP): "darkred",
        (Cloud.AWS, Cloud.AWS): "darkblue",
        (Cloud.GCP, Cloud.AWS): "plum",
        (Cloud.AWS, Cloud.GCP): "thistle",
    }
    rtt_colors = {
        (Cloud.GCP, Cloud.GCP): "darkgreen",
        (Cloud.AWS, Cloud.AWS): "darkorange",
        (Cloud.GCP, Cloud.AWS): "peru",
        (Cloud.AWS, Cloud.GCP): "saddlebrown",
    }


    marker = "."
    marker_size=1

    avg_rtt_line = __plot_series(
        "avg RTT",
        dist,
        avg_rtt,
        rtt_ax,
        "lower right",
        rtt_colors[cloudpair],
        unit="ms",
        bottom=0,
        top=300,
        semilogy=False,
        multiplot=multiplot,
        marker=marker,
        marker_size=marker_size
    )
    bitrate_line = __plot_series(
        f"bitrate",
        dist,
        bitrate,
        bitrate_ax,
        "upper right",
        color=bitrate_colors[cloudpair],
        unit="Mbps",
        bottom=1,
        top=10000,
        semilogy=True,
        multiplot=multiplot,
        marker=marker,
        marker_size=marker_size
    )
    return avg_rtt_line, bitrate_line


def __plot_series(
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
    multiplot: bool,
    marker: str,
marker_size:int) -> PathCollection:
    if semilogy:
        axis.set_yscale("log")
        ylabel = f"{unit} (log)"
        corr, _ = pearsonr(x, [log10(i) for i in y])
    else:
        ylabel = unit
        corr, _ = pearsonr(x, y)

    axis.set_ylabel(ylabel)

    plt.xlim(
        0, 17000
    )  # 20000 km is  half the circumf of earth, and the farthest pairs of data centers are 18000km
    axis.set_ylim(bottom, top)

    line = axis.scatter(
        x,
        y,
        color=color,
        marker=marker,
        s=marker_size,
        label=f"{series_name}\n(r={round(corr, 2)})",
    )

    if not multiplot:
        axis.legend(loc=loc)
    # __plot_linear_fit(axis, x, y, color, lbl=series_name, semilogy=semilogy)
    return line


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
