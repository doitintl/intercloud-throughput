#!/usr/bin/env bash

set -x
set -e
set -u
export SG=intercloud



# Check that variables are set

[ -v $RUN_ID ]
[ -v $SERVER_PUBLIC_ADDRESS ]
[ -v $CLIENT_PUBLIC_ADDRESS ]
[ -v $SERVER_CLOUD ]
[ -v $CLIENT_CLOUD ]
[ -v $SERVER_REGION ]
[ -v $CLIENT_REGION ]
[ -v $BASE_KEYNAME ]


CLIENT_REGION_KEYNAME=${BASE_KEYNAME}-${CLIENT_REGION}
CLIENT_REGION_KEYFILE=./aws-pems/${CLIENT_REGION_KEYNAME}.pem

set +e
IPERF_OUTPUT=""
N=10
while ((  $N > 0 )) && [[ -z $IPERF_OUTPUT ]]; do
  IPERF_OUTPUT=$(ssh -oStrictHostKeyChecking=no -i "$CLIENT_REGION_KEYFILE" ec2-user@"$CLIENT_PUBLIC_ADDRESS"  "iperf -c $SERVER_PUBLIC_ADDRESS -y C" )
  N=$(( N-1 ))
  sleep 2
done

if [[ -z "$IPERF_OUTPUT" ]]; then
 >&2 echo "No IPERF_OUTPUT"
 exit 233
fi
set -e
export BITRATE
BITRATE=$(echo "$IPERF_OUTPUT" | awk -F, '{print  $(NF-1) }' )

set +e
PING_OUTPUT=""
N=10
while ((  $N > 0 )) && [[ -z $PING_OUTPUT ]]; do
  PING_OUTPUT=$(ssh -oStrictHostKeyChecking=no -i "$CLIENT_REGION_KEYFILE" ec2-user@"$CLIENT_PUBLIC_ADDRESS"  "ping $SERVER_PUBLIC_ADDRESS -c 5" |tail -n 1)
  N=$(( N-1 ))
  sleep 2
done

if [[ -z "$PING_OUTPUT" ]]; then
 >&2 echo "No PING_OUTPUT"
 exit 223
fi
set -e

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