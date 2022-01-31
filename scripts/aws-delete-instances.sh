#!/usr/bin/env bash

set -x
set -e
set -u

CLIENT_INSTANCE_IDS=$(aws ec2 describe-instances --region $REGION --query 'Reservations[].Instances[].InstanceId' --filters "Name=tag:run-id,Values=${RUN_ID}" --output text)

if [[ -z $CLIENT_INSTANCE_IDS ]]; then
 >&2 echo "Cannot find instances with filter ${RUN_ID}"
 exit 101
fi
IFS=', ' read -r -a CLIENT_INSTANCE_IDS_ARR <<< "$CLIENT_INSTANCE_IDS"

aws ec2 terminate-instances --region $REGION --instance-ids ${CLIENT_INSTANCE_IDS_ARR}
