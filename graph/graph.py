import logging
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib import pyplot

from history.results import load_results_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

def graph_full_testing_history():
    results = load_results_csv()
    if not results:
        raise ValueError
    results.sort(key=lambda d: d["distance"])
    # Next, eliminate intra-zone tests
    results = list( filter(
        lambda d: ((d["from_cloud"], d["from_region"])!=(d["to_cloud"], d["to_region"])
                   ), results
    )  )# Must listify to use the filter iterator twice
    dist = [r["distance"] for r in results]
    bitrate = [ r["bitrate_Bps"] / 1e7 for r in results]
    avgRtt=[ r["avgrtt"]  for r in results]
    logging.info("Distance in [%s,%s]; Bitrate in [%s,%s]", round(min(dist),1), round(max(dist),1), round(min(bitrate),1), round(max(bitrate),1))


    # naming the x axis
    plt.xlabel("distance")
    # naming the y axis
    plt.ylabel("..")
    plt.plot(dist,bitrate, label="bitrate (10 MBps)")
    plt.plot(dist,avgRtt, label="avgrtt")

    plt.legend()
    # giving a title to my graph
    plt.title("Distance to latency & throughput")
    date_s=datetime.now().isoformat().replace(":","-")
    pyplot.savefig(f"./charts/{date_s}.png")

    plt.show()

if __name__ =="__main__":
    graph_full_testing_history()