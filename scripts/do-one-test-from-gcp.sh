#!/usr/bin/env bash

set -x
set -e
set -u

# Check that variables are set

IPERF_OUTPUT=""

set +e
N=10
while ((  N > 0 )) && [[ -z "$IPERF_OUTPUT" ]]; do
    sleep 3
    # Could do iperf -d for twoway
    IPERF_OUTPUT=$(gcloud compute ssh "$CLIENT_NAME"  --zone="${CLIENT_ZONE}" --command "iperf -c $SERVER_PUBLIC_ADDRESS -y C" )
    N=$(( N-1 ))
done
set -e
if [[ -z "$IPERF_OUTPUT" ]]; then
  exit 172
fi

export BITRATE
BITRATE=$(echo "$IPERF_OUTPUT" | awk -F, '{print  $(NF-1) }' )

PING_OUTPUT=$(gcloud compute ssh "$CLIENT_NAME"  --zone="${CLIENT_ZONE}" --command "ping $SERVER_PUBLIC_ADDRESS -c 5" |tail -n 1)

export AVG_RTT
AVG_RTT=$( echo "${PING_OUTPUT}" | awk -F= '{print $2}' | awk -F/ '{print $2}' )
export DATE_S
DATE_S=$( date -u +"%Y-%m-%dT%H:%M:%SZ" )

# The "return value"
jq --null-input -c \
 '{"timestamp": env.DATE_S,
  "run_id": env.RUN_ID,
  "from":  {"cloud": env.CLIENT_CLOUD, "region":env.CLIENT_REGION},
  "to": {"cloud": env.SERVER_CLOUD, "region": env.SERVER_REGION },
  "bitrate_Bps": env.BITRATE,
  "avgrtt": env.AVG_RTT }'