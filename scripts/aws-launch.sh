#!/usr/bin/env bash
set -x
set -e
set -u

# Check that variables are set


SG=intercloud-sg

INIT_SCRIPT=aws-install-and-run-iperf-server.sh


NAME="${REGION}-${RUN_ID}"
REGION_KEYNAME=${BASE_KEYNAME}-${REGION}
REGION_KEYFILE=./aws-pems/${REGION_KEYNAME}.pem

aws ec2 create-security-group --region "$REGION" --group-name $SG --description "For intercloud tests" > /dev/null || true
aws ec2 authorize-security-group-ingress --region "$REGION" --group-name $SG --protocol tcp --port 22 --cidr 0.0.0.0/0 > /dev/null || true
aws ec2 authorize-security-group-ingress --region "$REGION" --group-name $SG  --protocol tcp --port 5001 --cidr 0.0.0.0/0 > /dev/null ||true
aws ec2 authorize-security-group-ingress --region "$REGION" --group-name $SG  --protocol icmp --port -1  --cidr 0.0.0.0/0 > /dev/null  ||true


aws ec2 create-key-pair \
    --region "$REGION" \
    --key-name "$REGION_KEYNAME" \
    --query 'KeyMaterial' \
    --output text > "$REGION_KEYFILE" || true

chmod 400 "$REGION_KEYFILE" ||true


AMI=$(aws ec2 describe-images \
  --region "$REGION" \
  --owners amazon \
  --filters 'Name=name,Values=amzn2-ami-hvm-2.0.????????-x86_64-gp2' 'Name=state,Values=available' \
  --output json | \
    jq -r '.Images | sort_by(.CreationDate) | last(.[]).ImageId'
  )

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
FULLPATH_INIT_SCRIPT=$( realpath "$SCRIPT_DIR"/../startup-scripts/$INIT_SCRIPT)

CREATION_OUTPUT=$( aws ec2 run-instances \
  --region "$REGION" \
  --image-id "$AMI" \
  --security-group-ids intercloud-sg \
  --instance-type t2.nano \
  --key-name "$REGION_KEYNAME" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${NAME}},{Key=run-id,Value=${RUN_ID}}]" \
   --user-data file://"$FULLPATH_INIT_SCRIPT"
)

INSTANCE_ID=$( echo "$CREATION_OUTPUT" | jq -r ".Instances[0].InstanceId" )

#Alternative use  TARGET_STATE=running -- with  describe-instances, if you use that as below.
TARGET_STATE="passed"
STATUS="N/A"

# Try for up to approx 5 minutes, We hae seen init happen after 55 loops.
N=80
while ((  N > 0 )) && [[ "$STATUS" != "\"$TARGET_STATE\"" ]]; do
   STATUS=$(
     aws ec2 describe-instance-status --region "$REGION"  --instance-ids "$INSTANCE_ID"  --query "InstanceStatuses[0].InstanceStatus.Details[0].Status"
     # aws ec2 describe-instances --region eu-west-1 --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].State.Name'
    )

   N=$(( N-1 ))
   sleep 2
done

if [[ "$STATUS" != "\"$TARGET_STATE\"" ]]; then
   >&2 echo "Did not initialize in time"
   exit 171
fi

PUBLIC_DNS=$(
    aws ec2 describe-instances \
    --region "$REGION" \
    --instance-ids "$INSTANCE_ID"  \
    --query 'Reservations[0].Instances[0].PublicDnsName' | \
    jq -r .
  )


if [ -z "$PUBLIC_DNS" ]; then
  >&2 echo "No public DNS?"
  exit 1
fi

# The following line is the "Return value" of this script
echo "$PUBLIC_DNS"