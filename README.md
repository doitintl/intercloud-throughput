# Intercloud networking test

## Purpose

This runs a test of throughput and latency within and between regions in the same or different clouds.
 
## Article

See also the [related article](https://www.doit-intl.com/throughput-metrics-across-the-clouds/).
 
## What makes this different

Other cloud performance test benchmarks are available, but

* Most focus on latency, not throughput.
* Most are in a single cloud.
* This compares throughput to distance.

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
    * By default, the system will launch a VM in each region (so, about 47 VMs), then test all directed pairs (source and destination) among these VMs.
    * You can also do this in pieces as  as you learn the system. The system works incrementally, so  you can achieve full coverage by repeatedly running smaller test runs.
    * The number of VMs is equal to the number of regions. Tests are run between all the region-pairs, to efficently use launched VMs.
    * The number of total tests is  _O(n<sup>2</sup>)_),where _n_ is the number of regions.
    * Omitted: The system does not re-run already-run test-pairs (as listed in `results.csv`). However, you can specify these using `--region_pairs` (see below).
    * Omitted: The system does not do intraregion tests, where the source and destination are the same region. However, you can specify these using `--region_pairs` (see below).
    * Prioritization: If you are running batches of regions gradually, then where the system is selecting regions to test, it will interleave the different clouds in ordering the regions, so that  intercloud tests  go before intracloud tests; and will then  prioritize by choosing the least-tested regions, to spread out the testing.

* Options
    * Run `performance_test.py --help` for usage instructions.
    * You can run this repeatedly, accumulating more data in `results.csv`.
    * Options limit the regions-pairs that may be tested, but do not specify the exact list.
        * You can limit the number of regions tested in a "batch" (tested together, in parallel).
        * You can limit the number of such batches in a run.
        * You can limit which cloud-pairs can be included (AWS to AWS, GCP to AWS, AWS to GCP, GCP to GCP).
        * You can limit the minimum and maximum distance between source and destination data-center, e.g. if you want to focus on long-distance connections.
    * You can specify exactly which region-pairs to test (source and destination data-centers, where either can be in AWS or in GCP).
    * You can specify the instance (machine) type to use in each of AWS and GCP.

* Costs
    * Launching an instance in every region does not cost much: These small instances cost 0.5 - 2 cents per hour.
    * Because of parallelization, the test suite runs quickly.
    * Data volume is 10 MB per test.
    * This keeps down the compute and data egress charges.

## Reference data

### Enabled AWS regions

File `region_data/enabled_aws_regions.json` includes the default list of non-enabled and enabled AWS regions. If you delete that file, this  system will automatically detect which regions are enabled or not. Only enabled AWS regions participate in the testing.

### Locations of Data Centers

The distances are based on data-center locations gathered from various open sources. Though the cloud providers don’t
publicize the exact locations, these are not a secret either.

See directory `geoloc_data` for the data sources. The raw data was combined into `locations.csv`  by running `src/location_datasources/combine.py`

These locations should not be taken as exact. Each region is spread across multiple
(availability) zones, which in some cases are separated from each other by tens of kilometers, for robustness.  (See [Wikileaks](https://wikileaks.org/amazon-atlas/map/), which clearly illustrates that.) City-center coordinates are used as an approximation.

Yet given the speeds measured here, statistics that rely on approximate region location are precise enough that any error is swallowed inside other variations of network behavior.


## Output

* By default, the output goes under directory `results`.
    * You can change this by setting env variable `PERFTEST_RESULTSDIR`
* `results.csv` accumulates results.
* Charts are output to `charts` in that directory.
* For tracking the progress of testing:
    * `attempted-tests.csv` lists attempted tests, even ones that then fail.
    * `failed-to-create-vm.csv` lists cases where a VM could not be created.
    * `failed-tests.csv` lists failed tests, whether because a connection could not be made between VMs in the different
      regions or because a VM could not be created in the first place.
    * `tests-per-regionpair.csv` tracks the number of tests per region pair
      (so we can see if there were repeats, which does not happen unless `__region_pairs` are explicitly specified).

## How it works

1. Launches a VM in each specified region. See above on how regions are chosen.

* This is parallelized.

2. Runs a test between each directed region pair.

* All pairs across regions where there is a VM are tested.
    * You can override this with the `--region_pairs` option.
    * Tests are run in parallel, but a given region is involved in only one test at any one time, to avoid disrupting
      the results.

3. Deletes all VMs

* Deletion of AWS and GCP VMs are deleted in separate threads, in parallel.
* AWS VMs are deleted in parallel with each other, GCP VMs sequentially with each other.
* Regardless of how many tests succeed or fail, VMs are deleted at the end of the tests.
* If you kill the run in the middle, VMs might not get deleted.

## Generating charts

* Charts are generated automatically at the end of each test run, based on all data gathered in `results.csv`, not just the current test-run.
* Run `graph/plot_chart.py` (file is under `src`) to generate charts without a test run.

