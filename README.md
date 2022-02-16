# Intercloud networking test

## Purpose

This runs a test of throughput and latency within and between regions in the same or different clouds.

## What makes this different

Other cloud performance test benchmarks are available, but

* Most focus on latency, not throughput
* Most are in a single cloud.

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
    * The number of VMs is as the number of regions. Tests are run between all reahe most efficent tests
    * Omitted: Already-run test-pairs (as in `results.csv`) are not re-run. This allows you to run the process in
      several smaller runs, using the options below.
    * Omitted: Intraregion tests, where the source and destination were the same region, are not run. However, you can
      specify these using `--region_pairs` (see below).
    * Prioritization: Where not all possible regions are used (as with options, below, the system will interleave the
      different clouds in the priority list, to get intercloud tests first; and will choose the least-tested regions, to
      spread out the testing.)

* Options
    * Run `performance_test.py --help` for usage instructions.
    * You can specify exactly which region-pairs to test (source and destination data-centers, whether either can be in
      AWS or in GCP).
    * Other options limit the regions-pairs that may be tested, but do not specify the exact list. You can run this
      repeatedly, accumulating more data in `results.csv`.
        * You can limit the number of regions tested in a "batch"  (in parallel).
        * You can limit the number of such batches.
        * You can limit which cloud-pairs can be included (AWS to AWS, GCP to AWS, AWS to GCP, GCP to GCP)
        * You can limit the minimum and maximum distance between source and destinationd data-center, e.g. if you want
          to focus on long-distance networking.
    * You can specify the instance (machine) type to use in each of AWS and GCP.

* Costs
    * Launching an instance in every region does not cost much: These small instances cost 0.5 - 2 cents per hour.
    * Because of parallelization, the test suite runs quickly
    * Data volume is 10 MB per test.
    * This keeps down the compute and data egress charges.

## Locations of Data Centers

The distances are based on data-center locations gathered from various open sources. Though the cloud providers don’t
publicize the exact locations, these are not a secret either.

These locations should not be taken as exact. Each region is spread across multiple
(availability) zones, which in some cases are separated from each other by tens of kilometers, for robustness.  (
See [Wikileaks](https://wikileaks.org/amazon-atlas/map/), which clearly illustrates that.) City-center coordinates are
used as an approximation.

Yet given the speeds measured here, statistics that rely on approximate region location are precise enough that any
error is swallowed inside other variations of network behavior.

See directory `geoloc_data` for the data sources. The raw data is combined into  
`locations.csv`  by running `src/location_datasources/combine.py`

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

## How it works

1. Launches a VM in each specified region. See above on how regions are chosen.

* This is parallelized.

2. Runs a test between each directed region pair.

* All pairs across regions where there is a VM are tested.
    * You can override this with the `--region_pairs` option.
    * Tests are run in parallel, but a given region is involved in only one test at any one time, to avoid disrupting
      the results.

3. Deletes all VMs

* Regardless of how many tests succeed or fail).
* Deletion of AWS and GCP VMs are deleted in separate threads, in parallem
* AWS VMs are deleted in parallel with each other, GCP VMs sequentially with each other.

## Generating charts

* Charts are generated automatically at the end of each test run, based on all data gathered in `results.csv`
* Run `graph/plot_chart.py` (file is under `src`) to generate charts without a test run

