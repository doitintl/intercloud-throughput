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
* Initialized gcloud, with a default project set as gcloud config set project PROJECT_ID
* AWS with credentials in `~/.aws`
    * Permissions in each cloud allowing
        * create, describe, and delete for instances
        * GCP only: SSH to instances
        * AWS only: create security groups; create keys (PEM)
    * A default VPC, with Internet Gateway, in each region