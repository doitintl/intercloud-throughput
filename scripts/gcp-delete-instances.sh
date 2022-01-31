#!/usr/bin/env bash
set -x
set -e
set -u

TO_DELETE=$(gcloud compute instances list --filter "labels.run-id=$RUN_ID" --format "table[no-heading](NAME,ZONE)")
while IFS= read -r LINE; do
    NAME=$(echo "$LINE" |awk '{print $1}')
    ZONE=$(echo "$LINE" |awk '{print $2}')
    gcloud compute instances delete -q "${NAME}" --project="${PROJECT_ID}" --zone="${ZONE}"
done <<< "$TO_DELETE"
