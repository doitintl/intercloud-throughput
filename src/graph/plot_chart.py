import itertools
import logging
import os
import platform
import subprocess
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
from util import utils
from util.utils import set_cwd, process_starttime, process_starttime_iso


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
            % (results_dir(), perftest_resultsdir_envvar)
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
    datetime_s = process_starttime().strftime("%Y-%m-%dT%H-%M-%SZ")
    subdir = os.path.abspath(f"{results_dir()}/charts/{datetime_s}")
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

    _fig, base_ax = plt.subplots()
    rtt_ax = base_ax
    bitrate_ax = base_ax.twinx()

    plt.xlabel = "distance"

    if multiplot:
        __multiplot_figure(rtt_ax, bitrate_ax, clouddata)
    else:
        __singleplot_figure(
            bitrate, bitrate_ax, cloudpair, dist, multiplot, rtt, rtt_ax
        )

    plt.title(f"{__cloudpair_s(cloudpair)}: Distance to latency & throughput")

    chart_file = f"{subdir}/{__cloudpair_s(cloudpair)}{' by cloud pair' if multiplot else ''}.png"
    try:
        mkdir(os.path.dirname(os.path.realpath(chart_file)))
    except FileExistsError:
        pass
    pyplot.savefig(chart_file, dpi=300)

    plt.show()


def __singleplot_figure(bitrate, bitrate_ax, cloudpair, dist, multiplot, rtt, rtt_ax):
    plot_linear_rtt_func, plot_linear_bitrate_func = __plot_both_series(
        cloudpair, dist, rtt, bitrate, rtt_ax, bitrate_ax, multiplot
    )
    # noinspection PyArgumentList
    plot_linear_rtt_func()  # They don't overlap, so no need to adjust
    # noinspection PyArgumentList
    plot_linear_bitrate_func()


def __homogeneous(p: tuple[Any, Any]):
    return p[0] == p[1]


def __cloudpair_s(pair: tuple[Cloud, Cloud]) -> str:
    if pair is None:
        return "All Data"
    else:
        return f"{pair[0].name} to {pair[1].name}"


class EmptyDataset(Exception):
    pass


def __multiplot_figure(
    rtt_ax, bitrate_ax, clouddata: dict[Optional[tuple[Cloud, Cloud]], dict[str, list]]
):
    leftish_horiz = 0.30
    center_vert = 0.29
    lowerish = 0.1
    rightish = 0.73

    bitrate_legend_loc = "lower right"
    bitrate_legend_tag_xy = (rightish, center_vert)

    rtt_legend_loc = "lower center"
    rtt_legend_tag_xy = (leftish_horiz, lowerish)

    cloudpair_strs = []
    plot_linear_rtt_funcs = []
    plot_linear_bitrate_funcs = []

    clouddata = {k: v for k, v in clouddata.items() if k}  #

    # noinspection PyUnresolvedReferences
    def overlap_and_not(
        funcs: list[Callable[[Optional[int]], list[PathCollection]]]
    ) -> tuple[set[Callable], set[Callable]]:
        overlap: set[Callable] = set()
        not_overlap: set[Callable] = set()
        for f in funcs:
            for other in funcs:
                if other is f:
                    continue

                def close(p, q, ratio_epsilon):
                    avg = mean([p, q])
                    ratio = abs((p - q) / avg)
                    return ratio < ratio_epsilon

                slope_close = close(other.m, f.m, 0.01)
                intercept_close = close(other.b, f.b, 0.03)
                lines_overlap = slope_close and intercept_close
                if lines_overlap:
                    overlap.add(other)
                    overlap.add(f)

        for f in funcs:
            if f not in overlap:
                not_overlap.add(f)

        return overlap, not_overlap

    for j, (cloudpair, cpair_data) in enumerate(clouddata.items()):
        try:

            def plot_one_series_in_multiplot() -> tuple[
                Callable[[Optional[int]], list[PathCollection]],
                Callable[[Optional[int]], list[PathCollection]],
            ]:
                dist, rtt, bitrate = [
                    clouddata[cloudpair][k]
                    for k in ["distance", "avgrtt", "bitrate_Bps"]
                ]
                if not dist:
                    raise EmptyDataset
                return __plot_both_series(
                    cloudpair,
                    dist,
                    rtt,
                    bitrate,
                    rtt_ax,
                    bitrate_ax,
                    True,
                )

            (
                plot_linear_rtt,
                plot_linear_bitrate,
            ) = plot_one_series_in_multiplot()
        except EmptyDataset:
            continue
        plot_linear_rtt_funcs.append(plot_linear_rtt)
        plot_linear_bitrate_funcs.append(plot_linear_bitrate)
        cloudpair_strs.append(__cloudpair_s(cloudpair))

    def plot_linear(plotting_funcs) -> list[list[PathCollection]]:
        lines: list[list[PathCollection]] = []
        idx_overlap = 0
        overlapping, not_overlap = overlap_and_not(plotting_funcs)
        for f in plotting_funcs:
            if f in overlapping:
                ln = f(overlap_idx=idx_overlap)
                lines.append(ln)
                idx_overlap += 1
            else:
                ln = f()
                lines.append(ln)
        return lines

    rtt_lines = plot_linear(plot_linear_rtt_funcs)
    bitrate_lines = plot_linear(plot_linear_bitrate_funcs)

    def plot_legend_in_multiplot(
        lines: list[list[PathCollection]],
        series_name: str,
        ax,
        legend_loc: str,
        tag_xy: tuple[float, float],
    ):
        assert all(len(lst) == 1 for lst in lines)
        lines_flat = utils.shallow_flatten(lines)

        ax.legend(
            lines_flat, cloudpair_strs, loc=legend_loc
        )  # put legend into plot() in linear plot?

        ax.text(
            tag_xy[0],
            tag_xy[1],
            series_name,
            transform=ax.transAxes,
            fontsize=10,
        )

    plot_legend_in_multiplot(
        rtt_lines, "RTT", rtt_ax, rtt_legend_loc, rtt_legend_tag_xy
    )
    plot_legend_in_multiplot(
        bitrate_lines,
        "bitrate",
        bitrate_ax,
        bitrate_legend_loc,
        bitrate_legend_tag_xy,
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
    Callable[[Optional[int]], list[PathCollection]],
    Callable[[Optional[int]], list[PathCollection]],
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

    plot_linear_bitrate = __plot_series(
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
    )

    plot_linear_rtt = __plot_series(
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
    )
    return plot_linear_rtt, plot_linear_bitrate


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
) -> Callable[[Optional[int]], list[PathCollection]]:
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
    marker_size = 3
    axis.scatter(
        x,
        y,
        color=color,
        marker=marker,
        s=marker_size,
        alpha=0.2,
        label=f"{series_name}\n(r={round(corr, 2)})",
    )

    if not multiplot:
        axis.legend(loc=loc)

    plot_linear_func = __generate_linear_plot_func(
        cloudpair,
        axis,
        x,
        y,
        color,
        series_name=series_name,
        semilogy=semilogy,
    )

    return plot_linear_func


def __generate_linear_plot_func(
    cloudpair: tuple[Cloud, Cloud],
    ax: Axes,
    distance: list[float],
    y: list[float],
    color: str,
    series_name: str,
    semilogy: bool,
) -> Callable[[Optional[int]], list[PathCollection]]:
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

    def linear_plot_closure(overlap_idx: Optional[int] = None) -> list[PathCollection]:
        linewidth = 2
        adjustment = linewidth + 1
        if overlap_idx is None:
            # Could use overlap_idx 0 to indicate no overlap, but may want different color, linestayle, or alpha for ovverlapping
            b_adjusted = b
        else:
            b_adjusted = b + adjustment * overlap_idx

        y_linear = m * distance + b_adjusted
        if semilogy:
            y_linear = np.power(10, y_linear)

        try:
            line_list: list[PathCollection] = ax.plot(
                distance,
                y_linear,
                color=color,
                linewidth=linewidth,
                label=series_name,
            )
            return line_list
        except LinAlgError as lae:
            logging.error(
                f"No linear fit to {series_name} available",
            )
            raise lae

    linear_plot_closure.m = m
    linear_plot_closure.b = b

    return linear_plot_closure


if __name__ == "__main__":
    logging.info("Starting at %s", process_starttime_iso())
    set_cwd()
    graph_full_testing_history()
