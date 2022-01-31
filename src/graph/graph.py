import logging
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import pyplot
from numpy.linalg import LinAlgError

from cloud.clouds import interregion_distance, CloudRegion, Cloud, get_region
from history.results import load_results_csv, results_dir
from util.utils import set_cwd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def graph_full_testing_history():
    results = load_results_csv()
    if not results:
        raise ValueError(
            "No results in %s; maybe set another value for PERFTEST_RESULTSDIR env variable"
            % results_dir
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
        raise ValueError("No INTER-zone results")
    if len(results) < len_intra_and_interzone:
        logging.info(
            "Removed %d intrazone results", len(results) < len_intra_and_interzone
        )

    for d in results:
        d["distance"] = interregion_distance(
            get_region((d["from_cloud"]), d["from_region"]),
            get_region((d["to_cloud"]), d["to_region"]),
        )

    results.sort(key=lambda d: d["distance"])

    dist = [r["distance"] for r in results]
    bitrate = [r["bitrate_Bps"] / 1e7 for r in results]
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

    # naming the x axis
    plt.xlabel("distance")
    # naming the y axis
    plt.ylabel("..")
    plt.plot(dist, avg_rtt, color="r", label="avgrtt")
    plt.plot(dist, bitrate, color="blue", label="bitrate (10 MBps)")

    dist_np = np.array(dist)
    bitrate_np = np.array(bitrate)
    try:
        m_bitrate, b_bitrate = np.polyfit(dist_np, bitrate_np, 1)
    except LinAlgError as lae:
        logging.warning("%s: %s and %s", lae, dist_np[:10], bitrate_np[:10])
        m_bitrate, b_bitrate = 0, 0

    plt.plot(
        dist_np,
        m_bitrate * dist_np + b_bitrate,
        color="cyan",
        linestyle="dashed",
        label="bitrate linear fit (10 MBps)",
    )

    plt.legend()

    plt.title("Distance to latency & throughput")

    date_s = datetime.now().strftime("%Y-%m-%dT%H%-M-%S")
    chart_file = f"./charts/{date_s}.png"
    pyplot.savefig(chart_file)

    plt.show()
    logging.info("Generated chart %s", chart_file)


if __name__ == "__main__":
    set_cwd()
    graph_full_testing_history()
