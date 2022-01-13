#!/usr/bin/env bash

set -x
set -e
set -u
export SG=intercloud
export BASE_KEYNAME=intercloudperf


# Check that variables are set
>&2 echo "$RUN_ID"
>&2 echo "$SERVER_PUBLIC_ADDRESS"
>&2 echo "$CLIENT_PUBLIC_ADDRESS"
>&2 echo "$SERVER_CLOUD"
>&2 echo "$CLIENT_CLOUD"
>&2 echo "$SERVER_REGION"
>&2 echo "$CLIENT_REGION"

CLIENT_REGION_KEYNAME=${BASE_KEYNAME}-${CLIENT_REGION}
CLIENT_REGION_KEYFILE=${CLIENT_REGION_KEYNAME}.pem

# Could do perf -d for twoway
IPERF_OUTPUT=$(ssh -oStrictHostKeyChecking=no -i "$CLIENT_REGION_KEYFILE" ec2-user@"$CLIENT_PUBLIC_ADDRESS"  "iperf -c $SERVER_PUBLIC_ADDRESS -y C" )

>&2 echo "$IPERF_OUTPUT"

export BITRATE
BITRATE=$(echo "$IPERF_OUTPUT" | awk -F, '{print  $(NF-1) }' )

PING_OUTPUT=$(ssh -oStrictHostKeyChecking=no -i "$CLIENT_REGION_KEYFILE" ec2-user@"$CLIENT_PUBLIC_ADDRESS"  "ping $SERVER_PUBLIC_ADDRESS -c 5" |tail -n 1)

export AVG_RTT
AVG_RTT=$( echo "${PING_OUTPUT}" | awk -F= '{print $2}' | awk -F/ '{print $2}' )

export DATE_S
DATE_S=$( date -u +"%Y-%m-%dT%H:%M:%SZ" )


# The following is the "Return" value
jq --null-input -c \
 '{"datetime": env.DATE_S,
  "run_id": env.RUN_ID,
  "from":  {"cloud": env.CLIENT_CLOUD, "region":env.CLIENT_REGION},
  "to": {"cloud": env.SERVER_CLOUD, "region": env.SERVER_REGION },
  "bitrate_Bps": env.BITRATE,
  "avgrtt": env.AVG_RTT }'