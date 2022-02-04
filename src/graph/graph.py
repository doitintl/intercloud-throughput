import logging
import math
import os
from datetime import datetime
from os import mkdir

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import pyplot
from matplotlib.axes import Axes
from numpy.linalg import LinAlgError

from cloud.clouds import interregion_distance, get_region
from history.results import load_past_results, results_dir, perftest_resultsdir_envvar
from util.utils import set_cwd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)




def graph_full_testing_history():
    results = load_past_results()
    if not results:
        raise ValueError(
            "No results in %s; maybe set another value for %s env variable"
            % (results_dir, perftest_resultsdir_envvar)
        )
    len_intra_and_interzone = len(results)
    # Eliminate intra-zone tests
    ___results = list(
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

    dist = [r["distance"] for r in results]
    mega=1e6
    bitrate = [r["bitrate_Bps"] / mega for r in results]
    avg_rtt = [r["avgrtt"] for r in results]
    logging.info(
        "Distance in [%s,%s]; Bitrate in [%s,%s], RTT in [%s, %s]",
        round(min(dist), 1),
        round(max(dist), 1),
        round(min(bitrate), 1),
        round(max(bitrate), 1),
        round(min(avg_rtt), 1),
        round(max(avg_rtt), 1),
    )

    chart_file = __plot(dist, avg_rtt, bitrate)
    logging.info("Generated chart %s", chart_file)


def __plot(dist, avg_rtt, bitrate):

    fig, rtt_ax = plt.subplots()
    bitrate_ax = rtt_ax.twinx()

    plt.xlabel=("distance")

    __plot_rtt(dist, avg_rtt, rtt_ax)
    __plot_bitrate(dist, bitrate, bitrate_ax)

    plt.title("Distance to latency & throughput")
    datetime_s = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    chart_file = f"{results_dir}/charts/{datetime_s}.png"
    try:
        mkdir(os.path.dirname(os.path.realpath(chart_file)))
    except FileExistsError:
        pass
    pyplot.savefig(chart_file)
    plt.show()
    return chart_file


def __plot_rtt(dist, avg_rtt, rtt_ax):
    color_for_avg_rtt = "red"
    rtt_ax.set_ylabel("seconds")
    rtt_ax.plot(dist, avg_rtt, color=color_for_avg_rtt, label="avg rtt")
    rtt_ax.legend(loc="upper left")
    __plot_linear_fit(rtt_ax, dist, avg_rtt, color_for_avg_rtt)

def __plot_bitrate(dist, bitrate, bitrate_ax):
    color_for_bitrate = "blue"
    bitrate_ax.set_ylabel("Mbps")
    semilog_plot=True
    if semilog_plot:
        plot_func= bitrate_ax.semilogy
        bottom_limit=1
    else:
        plot_func=bitrate_ax.plot
        bottom_limit=0

    plot_func(dist, bitrate, color=color_for_bitrate, label="bitrate")
    bitrate_ax.legend(loc="upper right")
    #max_reasonable_bitrate = 1e10
    #bitrate_ax.set_ylim(bottom_limit, max_reasonable_bitrate )
    __plot_linear_fit(bitrate_ax, dist, bitrate,  color_for_bitrate, log=semilog_plot)


LinAlgError_counter = 0


def __plot_linear_fit(ax: Axes, dist, y, color, lbl=None, log=False):
    dist_np = np.array(dist)
    y_np = np.array(y)
    try:

        # noinspection PyTupleAssignmentBalance
        m, b = np.polyfit(dist_np, y_np, 1)
        if log:
            plot_func=ax.semilogy
        else:
            plot_func=ax.plot
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
