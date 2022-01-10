#!/usr/bin/env bash

set -x
set -e
set -u


# For both
export RUN_ID=$(( ( RANDOM % 900 )  + 100 ))
export SERVER_CLOUD=AWS
export BASE_KEYNAME=intercloudperf
export SG=intercloudperf-sg

#For launching the server using aws-one-instance.sh
export REGION=us-east-1
export CLIENTSVR=server
export INIT_SCRIPT=aws-install-and-run-iperf-server.sh
export WAIT_FOR_INIT=false

export SERVER_PUBLIC_DNS
SERVER_PUBLIC_DNS=$( ./aws-one-instance.sh )


# For  aws-client.sh
export SERVER_REGION=$REGION
export CLIENT_REGION=eu-west-1
./aws-client.sh


CLIENT_INSTANCE_ID=$(aws ec2 describe-instances --region $CLIENT_REGION --query 'Reservations[].Instances[].InstanceId' --filters "Name=tag:run-id,Values=${RUN_ID}" --output text)
aws ec2 terminate-instances --region $CLIENT_REGION --instance-ids "$CLIENT_INSTANCE_ID"

SERVER_INSTANCE_ID=$(aws ec2 describe-instances --region $SERVER_REGION --query 'Reservations[].Instances[].InstanceId' --filters "Name=tag:run-id,Values=${RUN_ID}" --output text)
aws ec2 terminate-instances --region $SERVER_REGION --instance-ids "$SERVER_INSTANCE_ID"



