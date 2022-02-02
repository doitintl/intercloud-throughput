# Intercloud networking test

## Purpose

* This runs a test of throughput and latency within and between regions in the same or different clouds.

## What makes it different

Other cloud performance test benchmarks are available, but most focus on latency, not throughput, and most are in a
single cloud.

## Latency vs Throughput

## Prerequisites

* Python 3.9
* bash
* jq
* realpath (on Mac, this is part of coreutils)
* Initialized gcloud, with a default project, set as `gcloud config set project PROJECT_ID`
* AWS with credentials in `~/.aws`
    * Permissions in each cloud allowing
        * create, describe, and delete for instances
        * GCP only: SSH to instances
        * AWS only: create security groups; create keys (PEM)
    * A default VPC, with Internet Gateway, in each region.
## Usage
* Run `pip install -r requirements.txt`, preferably in a virt env. Make sure you have Python 3.9 or above.
* Run `performance_test.py`
* Options: 
  * Run `performance_test.py --help`
  * By default, the system  will launch  a VM in each region (about 47 of these),  
then test all directed pairs (source and destination) among these VMs.
    * The number of total tests is of course _O(n<sup>2</sup>)_).
    * Already-run test-pairs (as in `results.csv`) are not re-run.
    * Intraregion tests,  where the source and destination were the same region, are omitted.
    * You can  limit the number of regions tested in a "batch"  (in parallel). 
    * You can limit the number of such batches.
    * Or you can specify exactly which region-pairs to test (source and destination, 
    each can be AWS or GCP).
    * You can run this repeatedly, accumulating more data in `results.csv`.
 
## Output
* By default, directory `results`. You can change this by setting env variable `PERFTEST_RESULTSDIR`
* See `results.csv`, which accumulates results.
* Graphs are output to `charts` in that directory.
* For tracking
   * `attempted-tests.csv` lists attempted tests, even ones that then fail.
   * `failed-tests.csv` lists failed tests.
   * `intraregion_tests.csv` lists tests where the source and destination were the same region.
   * `tests-per-regionpair.csv` tracks tests per region pair (so we can see if there were repeats).
