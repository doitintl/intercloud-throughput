#!/usr/bin/env bash
set -x
set -e
set -u

NAME="intercloud-${REGION}-${RUN_ID}"
ZONE=${REGION}-b

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
FULLPATH_INIT_SCRIPT=$(realpath "$SCRIPT_DIR"/../startup-scripts/gcp-install-and-run-iperf-server.sh)

CREATION_OUTPUT=$(gcloud compute instances create "${NAME}" \
   --project=${PROJECT_ID} \
   --zone=${ZONE} \
  --machine-type=e2-micro \
  --network-interface=network-tier=PREMIUM \
  --labels=run-id=$RUN_ID \
  --metadata-from-file=startup-script=$FULLPATH_INIT_SCRIPT
  )


SERVER_EXT_IP=$( echo $CREATION_OUTPUT | tail -1|awk '{print  $(NF-1) }' )
# The "Return value"
echo "$SERVER_EXT_IP,$NAME,$ZONE"
