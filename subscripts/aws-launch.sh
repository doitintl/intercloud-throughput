#!/usr/bin/env bash
set -x
set -e
set -u


# Check that variables are set
>&2 echo $RUN_ID
>&2 echo $REGION

export CLIENTSVR=server
export SG=intercloud
export BASE_KEYNAME=intercloudperf
export INIT_SCRIPT=aws-install-and-run-iperf-server.sh
export WAIT_FOR_INIT=true
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

SERVER_ADDRESS=$("$SCRIPT_DIR"/aws-one-instance.sh)
echo $SERVER_ADDRESS
