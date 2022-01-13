#!/usr/bin/env bash

set -x
set -e
set -u

# Check that variables are set
>&2 echo "$RUN_ID"
>&2 echo "$SERVER_PUBLIC_DNS"
>&2 echo "$SERVER_CLOUD"
>&2 echo "$SERVER_REGION"
>&2 echo "$BASE_KEYNAME"
>&2 echo "$SG"
>&2 echo "$CLIENT_REGION"


#  For  aws-one-instance.sh (together with some of those that were exported into this file, above)
export CLIENTSVR=client
export REGION=$CLIENT_REGION
export INIT_SCRIPT=aws-install-iperf.sh
export WAIT_FOR_INIT=true

CLIENT_PUBLIC_DNS=$( ./aws-one-instance.sh )

REGION_KEYNAME=${BASE_KEYNAME}-${REGION}
REGION_KEYFILE=${REGION_KEYNAME}.pem
#ssh-keyscan -H $CLIENT_PUBLIC_DNS >> ~/.ssh/known_hosts

# Could do perf -d for twoway
IPERF_OUTPUT=$(ssh -oStrictHostKeyChecking=no -i "$REGION_KEYFILE" ec2-user@$CLIENT_PUBLIC_DNS  "iperf -c $SERVER_PUBLIC_DNS -y C" )

echo $IPERF_OUTPUT
export BITRATE
BITRATE=$(echo $IPERF_OUTPUT | awk -F, '{print  $(NF-1) }' )


PING_OUTPUT=$(ssh -oStrictHostKeyChecking=no -i "$REGION_KEYFILE" ec2-user@$CLIENT_PUBLIC_DNS  "ping $SERVER_PUBLIC_DNS -c 5" |tail -n 1)

export AVG_RTT
AVG_RTT=$( echo ${PING_OUTPUT} | awk -F= '{print $2}' | awk -F/ '{print $2}' )
export DATE_S
DATE_S=$( date -u +"%Y-%m-%dT%H:%M:%SZ" )

export CLIENT_CLOUD=AWS


jq --null-input -c \
 '{"datetime": env.DATE_S,
  "from":  {"cloud": env.CLIENT_CLOUD, "region":env.CLIENT_REGION},
  "to": {"cloud": env.SERVER_CLOUD, "region": env.SERVER_REGION },
  "bitrate_Bps": env.BITRATE,
  "avgrtt": env.AVG_RTT }' >results.jsonl