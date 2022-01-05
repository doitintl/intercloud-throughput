#!/usr/bin/env bash
set -x
set -e
set -u
RUN_ID=$(( ( RANDOM % 900 )  + 100 ))

CLOUD=GCP
PROJECT_ID=joshua-playground

SERVER_REGION=us-east1
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


CLIENT_REGION=us-central1
CLIENT_NAME="client-${CLIENT_REGION}-${RUN_ID}"
CLIENT_ZONE="${CLIENT_REGION}-b"

gcloud compute instances create ${CLIENT_NAME} \
   --project=${PROJECT_ID} \
   --zone=${CLIENT_ZONE} \
   --machine-type=e2-micro \
   --network-interface=network-tier=PREMIUM  \
   --metadata-from-file=startup-script=gcp-install-iperf.sh

# Could do -d for twoway
IPERF_OUTPUT=$(gcloud compute ssh $CLIENT_NAME  --zone=${CLIENT_ZONE} --command "iperf -c $SERVER_EXT_IP -y C" )

BITRATE=$(echo $IPERF_OUTPUT | awk -F, '{print  $(NF-1) }' )
BITRATE_HUMAN=$(echo $BITRATE | numfmt --to=iec-i  )

PING_OUTPUT=$(gcloud compute ssh $CLIENT_NAME  --zone=${CLIENT_ZONE} --command "ping $SERVER_EXT_IP -c 5" |tail -n 1)

AVG_RTT=$( echo ${PING_OUTPUT} | awk -F= '{print $2}' | awk -F/ '{print $2}' )
DATE_S=$( date -u +"%Y-%m-%dT%H:%M:%SZ" )

echo "${DATE_S}: From $CLOUD $CLIENT_REGION to $SERVER_REGION ${BITRATE_HUMAN}B/sec and avg RTT $AVG_RTT" >>results.txt




gcloud compute instances delete -q ${SERVER_NAME} \
   --project=${PROJECT_ID} \
   --zone=${SERVER_ZONE}

gcloud compute instances delete -q ${CLIENT_NAME} \
   --project=${PROJECT_ID} \
   --zone=${CLIENT_ZONE}
