#!/usr/bin/env bash
set -x
set -e
set -u
RUN_ID=$(( ( RANDOM % 900 )  + 100 ))

export SERVER_CLOUD="GCP"
export CLIENT_CLOUD="GCP"

PROJECT_ID=joshua-playground

export SERVER_REGION=us-east1
SERVER_NAME="server-${SERVER_REGION}-${RUN_ID}"
SERVER_ZONE=${SERVER_REGION}-b

SERVER_CREATION_OUTPUT=$(gcloud compute instances create ${SERVER_NAME} \
   --project=${PROJECT_ID} \
   --zone=${SERVER_ZONE} \
  --machine-type=e2-micro \
  --network-interface=network-tier=PREMIUM \
  --metadata-from-file=startup-script=gcp-install-and-run-iperf-server.sh
  )


SERVER_EXT_IP=$( echo $SERVER_CREATION_OUTPUT | tail -1|awk '{print  $(NF-1) }' )


export CLIENT_REGION=us-central1
CLIENT_NAME="client-${CLIENT_REGION}-${RUN_ID}"
CLIENT_ZONE="${CLIENT_REGION}-b"

gcloud compute instances create ${CLIENT_NAME} \
   --project=${PROJECT_ID} \
   --zone=${CLIENT_ZONE} \
   --machine-type=e2-micro \
   --network-interface=network-tier=PREMIUM  \
   --metadata-from-file=startup-script=gcp-install-iperf.sh



IPERF_OUTPUT=""

set +e
N=3
while ((  $N > 0 )) && [[ -z "$IPERF_OUTPUT" ]]; do
    sleep 3
    # Could do iperf -d for twoway
    IPERF_OUTPUT=$(gcloud compute ssh $CLIENT_NAME  --zone=${CLIENT_ZONE} --command "iperf -c $SERVER_EXT_IP -y C" )
    N=$(( N-1 ))
done
set -e
if [[ -z "$IPERF_OUTPUT" ]]; then
  exit 1
fi

BITRATE=$(echo $IPERF_OUTPUT | awk -F, '{print  $(NF-1) }' )
export BITRATE_HUMAN

BITRATE_HUMAN=$(echo $BITRATE | numfmt --to=iec-i  )
PING_OUTPUT=$(gcloud compute ssh $CLIENT_NAME  --zone=${CLIENT_ZONE} --command "ping $SERVER_EXT_IP -c 5" |tail -n 1)

export AVG_RTT
AVG_RTT=$( echo ${PING_OUTPUT} | awk -F= '{print $2}' | awk -F/ '{print $2}' )
export DATE_S
DATE_S=$( date -u +"%Y-%m-%dT%H:%M:%SZ" )


jq --null-input -c \
 '{"datetime": env.DATE_S,
  "from":  {"cloud": env.CLIENT_CLOUD, "region":env.CLIENT_REGION},
  "to": {"cloud": env.SERVER_CLOUD, "region": env.SERVER_REGION },
  "bitrate_Bps": env.BITRATE_HUMAN,
  "avgrtt": env.AVG_RTT }' >results.jsonl

gcloud compute instances delete -q ${SERVER_NAME} \
   --project=${PROJECT_ID} \
   --zone=${SERVER_ZONE}

gcloud compute instances delete -q ${CLIENT_NAME} \
   --project=${PROJECT_ID} \
   --zone=${CLIENT_ZONE}
