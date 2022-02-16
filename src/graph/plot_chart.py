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
from typing import Optional, Any, Callable

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

LinAlgError_counter = 0


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
        rtt = data["avgrtt"]
        assert len(dist) == len(bitrate) == len(rtt)
        mean_bitrate = mean(
            [log10(bitrate[i]) / dist[i] for i in range(len(dist)) if dist[i] != 0]
        )

        bitrate_s += "\t%s: %s\n" % (
            __cloudpair_s(cloudpair),
            round(bitrate_multiplier * mean_bitrate, 1),
        )

        mean_avgrtt = mean([rtt[j] / dist[j] for j in range(len(dist)) if dist[j] != 0])
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

    def homogeneous_first(p: tuple[Cloud, Cloud]):
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
            __plot_figure(None, data_by_cloudpair, subdir, multiplot=True)
        else:
            __plot_figure(cloudpair, data_by_cloudpair, subdir, multiplot=False)

    if platform.system() == "Darwin":
        subprocess.call(["open", subdir])


def __plot_figure(
    cloudpair: Optional[tuple[Cloud, Cloud]],
    clouddata: dict[Optional[tuple[Cloud, Cloud]]],
    subdir: str,
    multiplot: bool,
):
    dist, rtt, bitrate = [
        clouddata[cloudpair][k] for k in ["distance", "avgrtt", "bitrate_Bps"]
    ]

    if not dist:  # No data
        return

    # fig = plt.figure(count) We use _fig as below

    _fig, base_ax = plt.subplots()
    rtt_ax = base_ax
    bitrate_ax = base_ax.twinx()

    plt.xlabel = "distance"

    if not multiplot:
        __singleplot_figure(
            bitrate, bitrate_ax, cloudpair, dist, multiplot, rtt, rtt_ax
        )
    else:
        __multiplot_figure(rtt_ax, bitrate_ax, clouddata)

    plt.title(f"{__cloudpair_s(cloudpair)}: Distance to latency & throughput")

    chart_file = f"{subdir}/{__cloudpair_s(cloudpair)}{' by cloud pair' if multiplot else ''}.png"
    try:
        mkdir(os.path.dirname(os.path.realpath(chart_file)))
    except FileExistsError:
        pass
    pyplot.savefig(chart_file)

    plt.show()


def __singleplot_figure(bitrate, bitrate_ax, cloudpair, dist, multiplot, rtt, rtt_ax):
    _, _, plot_linear_rtt, plot_linear_bitrate = __plot_both_series(
        cloudpair, dist, rtt, bitrate, rtt_ax, bitrate_ax, multiplot
    )
    plot_linear_rtt()  # They don't overlap, so no need to adjust
    plot_linear_bitrate()


def __homogeneous(p: tuple[Any, Any]):
    return p[0] == p[1]


def __cloudpair_s(pair: tuple[Cloud, Cloud]) -> str:
    if pair is None:
        return "All Data"
    else:
        return f"{pair[0].name} to {pair[1].name}"


def __multiplot_figure(
    rtt_ax, bitrate_ax, clouddata: dict[Optional[tuple[Cloud, Cloud]], dict[str, list]]
):
    leftish_horiz = 0.30
    center_vert = 0.29
    lowerish = 0.1
    rightish = 0.73

    bitrate_legend_loc_ = "lower right"
    bitrate_legend_tag_xy = (rightish, center_vert)

    rtt_legend_loc = "lower center"
    rtt_legend_tag_xy = (leftish_horiz, lowerish)

    labels = []
    rtt_lines = []
    bitrate_lines = []
    plot_linear_rtt_funcs = []
    plot_linear_bitrate_funcs = []

    clouddata = {k: v for k, v in clouddata.items() if k}  #

    for j, (cloudpair_, cpair_data) in enumerate(clouddata.items()):
        __plot_one_series_in_multiplot(
            cloudpair_,
            clouddata,
            rtt_ax,
            bitrate_ax,
            plot_linear_rtt_funcs,
            plot_linear_bitrate_funcs,
            rtt_legend_loc,
            bitrate_legend_loc_,
            rtt_legend_tag_xy,
            bitrate_legend_tag_xy,
            labels,
            rtt_lines,
            bitrate_lines,
        )

    def plot_linear(plotting_funcs):
        overlapping, not_overlap = __overlap_and_not(plotting_funcs)
        for i, linear_plot_func in enumerate(overlapping):
            linear_plot_func(num_overlapping=len(overlapping), overlap_idx=i)  #
        for linear_plot_func in not_overlap:
            linear_plot_func()

    plot_linear(plot_linear_rtt_funcs)
    plot_linear(plot_linear_bitrate_funcs)


def __overlap_and_not(funcs: list[Callable[[int], None]]) -> tuple[list, list]:
    overlap: list[Callable] = []
    not_overlap: list[Callable] = []

    for f in funcs:
        for other in funcs:

            def close(p, q, ratio_epsilon):
                avg = mean([p, q])
                return abs((p - q) / avg) < ratio_epsilon

            # noinspection PyUnresolvedReferences
            lines_overlap = close(other.m, f.m, 0.01) and close(other.b, f.b, 0.03)
            if other is not f and other not in overlap and lines_overlap:
                overlap.append(other)

    for f in funcs:
        if f not in overlap:
            not_overlap.append(f)

    assert len(not_overlap) + len(overlap) == len(
        funcs
    ), f"{len(not_overlap)} + {len(overlap)} != {len(funcs)}"
    return overlap, not_overlap


def __plot_one_series_in_multiplot(
    cloudpair: tuple[Cloud, Cloud],
    clouddata: dict[Optional[tuple[Cloud, Cloud]], dict[str, list]],
    rtt_ax,
    bitrate_ax,
    plot_linear_rtt_funcs_inout: list[Callable],
    plot_linear_bitrate_funcs_inout: list[Callable],
    rtt_legend_loc: str,
    bitrate_legend_loc: str,
    rtt_legend_tag_xy: tuple[float, float],
    bitrate_legend_tag_xy: tuple[float, float],
    labels_inout: list[str],
    rtt_lines_inout: list[PathCollection],
    bitrate_lines_inout: list[PathCollection],
):
    dist, rtt, bitrate = [
        clouddata[cloudpair][k] for k in ["distance", "avgrtt", "bitrate_Bps"]
    ]
    if not dist:
        return
    (
        rtt_line,
        bitrate_line,
        plot_linear_rtt,
        plot_linear_bitrate,
    ) = __plot_both_series(
        cloudpair,
        dist,
        rtt,
        bitrate,
        rtt_ax,
        bitrate_ax,
        True,
    )
    plot_linear_rtt_funcs_inout.append(plot_linear_rtt)
    plot_linear_bitrate_funcs_inout.append(plot_linear_bitrate)
    labels_inout.append(__cloudpair_s(cloudpair))
    rtt_lines_inout.append(rtt_line)
    bitrate_lines_inout.append(bitrate_line)

    rtt_ax.legend(rtt_lines_inout, labels_inout, loc=bitrate_legend_loc)
    bitrate_ax.legend(bitrate_lines_inout, labels_inout, loc=rtt_legend_loc)

    rtt_ax.text(
        rtt_legend_tag_xy[0],
        rtt_legend_tag_xy[1],
        "RTT",
        transform=rtt_ax.transAxes,
        fontsize=10,
    )
    bitrate_ax.text(
        bitrate_legend_tag_xy[0],
        bitrate_legend_tag_xy[1],
        "bitrate",
        transform=bitrate_ax.transAxes,
        fontsize=10,
    )


def __plot_both_series(
    cloudpair: tuple[Cloud, Cloud],
    dist: list,
    rtt: list,
    bitrate: list,
    rtt_ax,
    bitrate_ax,
    multiplot: bool,
) -> tuple[
    PathCollection, PathCollection, Callable[[int], None], Callable[[int], None]
]:
    bitrate_colors = {
        (Cloud.GCP, Cloud.GCP): "darkred",
        (Cloud.AWS, Cloud.AWS): "darkblue",
        (Cloud.GCP, Cloud.AWS): "plum",
        (Cloud.AWS, Cloud.GCP): "thistle",
    }
    rtt_colors = {
        (Cloud.GCP, Cloud.GCP): "red",
        (Cloud.AWS, Cloud.AWS): "blue",
        (Cloud.GCP, Cloud.AWS): "purple",
        (Cloud.AWS, Cloud.GCP): "orange",
    }

    marker = "."
    marker_size = 1

    bitrate_line, plot_linear_bitrate = __plot_series(
        cloudpair,
        series_name=f"bitrate",
        x=dist,
        y=bitrate,
        axis=bitrate_ax,
        loc="lower right",
        color=bitrate_colors[cloudpair],
        unit="Mbps",
        bottom=1,
        top=10000,
        semilogy=True,
        multiplot=multiplot,
        marker=marker,
        marker_size=marker_size,
    )

    rtt_line, plot_linear_rtt = __plot_series(
        cloudpair,
        series_name="RTT",
        x=dist,
        y=rtt,
        axis=rtt_ax,
        loc="upper right",
        color=rtt_colors[cloudpair],
        unit="ms",
        bottom=0,
        top=300,
        semilogy=False,
        multiplot=multiplot,
        marker=marker,
        marker_size=marker_size,
    )
    return rtt_line, bitrate_line, plot_linear_rtt, plot_linear_bitrate


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
    multiplot: bool,
    marker: str,
    marker_size: int,
) -> tuple[PathCollection, Callable[[int], None]]:
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

    plot_linear = __calc_linear_fit(
        cloudpair,
        axis,
        x,
        y,
        color,
        series_name=series_name,
        semilogy=semilogy,
    )

    return line, plot_linear


def __calc_linear_fit(
    cloudpair: tuple[Cloud, Cloud],
    ax: Axes,
    distance: list[float],
    y: list[float],
    color: str,
    series_name: str,
    semilogy: bool,
) -> Callable[[int], None]:
    """
    :return function that actually does the plotting. We do this because
    we need to gather the different lines (slope m nd intercept b) to compare to
    see if they overlap, then adjust so that they don't hide each other.
    Unfortunately this results in some complexity as this function object is passed all
    the way up the stack.
    """
    distance = np.array(distance)
    y = np.array(y)

    if semilogy:
        y = np.log10(y)

    # noinspection PyTupleAssignmentBalance
    returned = np.polyfit(distance, y, 1, full=True)
    m, b = returned[0]
    logging.debug(
        "%s %s: slope %f intercept %f", __cloudpair_s(cloudpair), series_name, m, b
    )
    y_linear = m * distance + b
    if semilogy:
        y_linear = np.power(10, y_linear)

    def linear_plot_func(num_overlapping: int = 0, overlap_idx: int = 0):
        """If num_overlapping is 0, overlap_idx is ignored"""
        if num_overlapping == 0:
            assert overlap_idx == 0
        if num_overlapping > 0:
            assert overlap_idx < num_overlapping

        assert (
            num_overlapping <= 3
        ), "Up to 3 are supported (since it is imposssible to draw a huge number of overlapping)"

        if not num_overlapping:
            y_linear_adjusted = y_linear
        else:
            adjustments = []
            base_adj = 4
            for i in range(len(y_linear)):
                if overlap_idx == i % num_overlapping:
                    if i % (2 * num_overlapping) == overlap_idx:
                        adj = 0.5 * base_adj
                    else:
                        adj = -0.5 * base_adj
                else:
                    adj = 0

                adjustments.append(adj)
            adjustments = np.array(adjustments)

            y_linear_adjusted = y_linear + adjustments

        alpha = 0.5 if overlap_idx else 1

        try:
            ax.plot(
                distance,
                y_linear_adjusted,
                color=color,
                linestyle=None,
                linewidth=3,
                alpha=alpha,
                label=series_name,
            )
        except LinAlgError as lae:
            global LinAlgError_counter
            LinAlgError_counter += 1
            logging.warning("%s: %s and %s", lae, distance[:10], y[:10])
            ax.text(
                2000,
                3500 - (LinAlgError_counter * 500),
                f"No linear fit to {series_name} available",
                fontsize=10,
                style="italic",
                bbox={"facecolor": "red", "alpha": 0.5, "pad": 3},
            )

    linear_plot_func.m = m
    linear_plot_func.b = b

    return linear_plot_func


if __name__ == "__main__":
    set_cwd()
    graph_full_testing_history()
