#!/usr/bin/env bash
aws ec2 describe-regions --output text

gcloud compute regions list --format "table[no-heading](NAME)"

#38.79600845911014, -77.61209005956113