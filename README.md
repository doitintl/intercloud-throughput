# Intercloud networking test

## Purpose

* This runs a test of throughput and latency within and between regions in the same or different clouds.

## What makes this different

Other cloud performance test benchmarks are available, but most focus on latency, not throughput, and most are in a
single cloud.

## Prerequisites

* Python 3.9
* Bash 5
* jq
* realpath (on Mac, this is part of coreutils)
* Initialized gcloud, with a default project, set as `gcloud config set project PROJECT_ID`
* AWS with credentials in `~/.aws`
    * Permissions in each cloud allowing
        * create, describe, and delete for instances
        * GCP only: SSH to instances
        * AWS only: create security groups; create keys (PEM)
    * In each region: A default VPC, with an Internet Gateway and a route (as normal) sending internet traffic through
      that Gateway.

## Usage

* Run `pip install -r requirements.txt`, preferably in a virtual environment. Make sure you have Python 3.9 or above.
* Run `performance_test.py --help` (file is under `src`) for usage.
* Behavior
    * By default, the system will launch a VM in each region (so, about 47 VMs),  
      then test all directed pairs (source and destination) among these VMs.
    * The number of total tests is of course _O(n<sup>2</sup>)_),where _n_ is the number of regions.
    * However, the number of VMs is as the number of regions. Tests are run between all reahe most efficent tests
    * Already-run test-pairs (as in `results.csv`) are not re-run.
    * Intraregion tests, where the source and destination were the same region, are omitted.

* Options
    * You can specify exactly which region-pairs to test (source and destination datacenters, whether either can be in
      AWS or in GCP).
    * Other options limit the regions-pairs that may be tested, but do not specify the exact list. You can run this
      repeatedly, accumulating more data in `results.csv`.
        * You can limit the number of regions tested in a "batch"  (in parallel).
        * You can limit the number of such batches.
        * You can limit which cloud-pairs can be included (AWS to AWS, GCP to AWS, AWS to GCP, GCP to GCP)
        * You can limit the minimum, and maximum distance between source and destinationd datacenter, e.g. if you want
          to focus on long-distance networking.

* Costs
    * Ultracheap are used, for an average price of about 0.8 cents per VM per hour.
    * Since each stage is fully parallelized, even a full test takes ten minutes.
    * Thus, the total price for a full test run is around 10 cents.

## Output

* By default, the output goes under directory `results`.
    * You can change this by setting env variable `PERFTEST_RESULTSDIR`
* `results.csv`, which accumulates results.
* Charts are output to `charts` in that directory.
* For tracking progress
    * `attempted-tests.csv` lists attempted tests, even ones that then fail.
    * `failed-to-create-vm.csv` lists cases where a VM could not be created.
    * `failed-tests.csv` lists failed tests, whether because a VM could not be created or because a connection could not
      be made between VMs in the different regions.
    * `tests-per-regionpair.csv` tracks the number of tests per region pair (so we can see if there were repeats).

## Generating charts

* Charts are generated automatically at the end of each test run, based on all data gathered in `results.csv`
* Run `graph/plot_chart.py` (file is under `src`) to generate charts without a test run

