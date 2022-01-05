#!/usr/bin/env bash

set -x
set -e
set -u
RUN_ID=$(( ( RANDOM % 900 )  + 100 ))
CLOUD=AWS

BASE_KEYNAME=icld

SG=intercloud-sg

#SERVER_REGION=us-west-2
#SERVER_NAME="server-${SERVER_REGION}-${RUN_ID}"
#SERVER_REGION_KEYNAME=$BASE_KEYNAME--${SERVER_REGION}
#SERVER_REGION_KEYFILE=${SERVER_REGION_KEYNAME}.pem
#
#aws ec2 create-security-group --region $SERVER_REGION --group-name $SG --description "For intercloud tests" || true
#aws ec2 authorize-security-group-ingress --region $SERVER_REGION --group-name $SG --protocol tcp --port 22 --cidr 0.0.0.0/0 || true
#aws ec2 authorize-security-group-ingress --region $SERVER_REGION --group-name $SG  --protocol tcp --port 5001 --cidr 0.0.0.0/0  ||true
#
#
#aws ec2 create-key-pair \
#  --region $SERVER_REGION \
#  --key-name $KEYNAME \
#  --query 'KeyMaterial' \
#  --output text > $SERVER_REGION_KEYFILE || true
#
#chmod 400 $SERVER_REGION_KEYFILE ||true
#
#SERVER_AMI=$(aws ec2 describe-images \
#  --region $SERVER_REGION \
#  --owners amazon \
#  --filters 'Name=name,Values=amzn2-ami-hvm-2.0.????????-x86_64-gp2' 'Name=state,Values=available' \
#  --output json | \
#    jq -r '.Images | sort_by(.CreationDate) | last(.[]).ImageId'
#    )
#
#SERVER_CREATION_OUTPUT=$( aws ec2 run-instances \
#  --region $SERVER_REGION \
#  --image-id $SERVER_AMI \
#  --security-group-ids intercloud-sg \
#  --instance-type t2.nano \
#  --key-name $KEYNAME \
#  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${SERVER_NAME}}]" \
#   --user-data file://aws-install-and-run-iperf-server.sh
#)
#SERVER_INSTANCE_ID=$( echo $SERVER_CREATION_OUTPUT | jq -r ".Instances[0].InstanceId" )
#
#SERVER_EXT_IP=$(
#  aws ec2 describe-instances \
#  --region $SERVER_REGION \
#  --instance-ids $SERVER_INSTANCE_ID  \
#  --query 'Reservations[0].Instances[0].PublicIpAddress' | \
#  jq -r .
#  )






 

CLIENT_REGION=eu-west-1
CLIENT_NAME="client-${CLIENT_REGION}-${RUN_ID}"
CLIENT_REGION_KEYNAME=${BASE_KEYNAME}-${CLIENT_REGION}
CLIENT_REGION_KEYFILE=${CLIENT_REGION_KEYNAME}.pem


aws ec2 create-security-group --region $CLIENT_REGION --group-name $SG --description "For intercloud tests" || true
aws ec2 authorize-security-group-ingress --region $CLIENT_REGION --group-name $SG --protocol tcp --port 22 --cidr 0.0.0.0/0 || true
aws ec2 authorize-security-group-ingress --region $CLIENT_REGION --group-name $SG  --protocol tcp --port 5001 --cidr 0.0.0.0/0  ||true


aws ec2 create-key-pair \
  --region $CLIENT_REGION \
  --key-name $CLIENT_REGION_KEYNAME \
  --query 'KeyMaterial' \
  --output text > "$CLIENT_REGION_KEYFILE" || true

chmod 400 "$CLIENT_REGION_KEYFILE" ||true

CLIENT_AMI=$(aws ec2 describe-images \
  --region $CLIENT_REGION \
  --owners amazon \
  --filters 'Name=name,Values=amzn2-ami-hvm-2.0.????????-x86_64-gp2' 'Name=state,Values=available' \
  --output json | \
    jq -r '.Images | sort_by(.CreationDate) | last(.[]).ImageId'
  )


CLIENT_CREATION_OUTPUT=$( aws ec2 run-instances \
  --region $CLIENT_REGION \
  --image-id "$CLIENT_AMI" \
  --security-group-ids intercloud-sg \
  --instance-type t2.nano \
  --key-name $CLIENT_REGION_KEYNAME \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${CLIENT_NAME}}]" \
   --user-data file://aws-install-iperf.sh
)

CLIENT_INSTANCE_ID=$( echo "$CLIENT_CREATION_OUTPUT" | jq -r ".Instances[0].InstanceId" )

CLIENT_EXT_IP=$(
  aws ec2 describe-instances \
  --region $CLIENT_REGION \
  --instance-ids "$CLIENT_INSTANCE_ID"  \
  --query 'Reservations[0].Instances[0].PublicIpAddress' | \
  jq -r .
  )

CLIENT_STATUS="initializing"
while [[ "$CLIENT_STATUS" != "\"passed\"" ]]; do

   CLIENT_STATUS=$(
     aws ec2 describe-instance-status --region $CLIENT_REGION  --instance-ids "$CLIENT_INSTANCE_ID" \
       --query "InstanceStatuses[0].InstanceStatus.Details[0].Status"
     )

    sleep 1
done

# Could do -d for twoway
IPERF_OUTPUT=$(ssh -i $CLIENT_REGION_KEYFILE ec2_user@$CLIENT_EXT_IP  "iperf -c $SERVER_EXT_IP -y C" )


echo $IPERF_OUTPUT
BITRATE=$(echo $IPERF_OUTPUT | awk -F, '{print  $(NF-1) }' )
BITRATE_HUMAN=$(echo $BITRATE | numfmt --to=iec-i  )

PING_OUTPUT=$(ssh -i $CLIENT_REGION_KEYFILE ec2_user@$CLIENT_EXT_IP  "iperf -c $SERVER_EXT_IP -y C" |tail -n 1)
echo $PING_OUTPUT

AVG_RTT=$( echo ${PING_OUTPUT} | awk -F= '{print $2}' | awk -F/ '{print $2}' )
DATE_S=$( date -u +"%Y-%m-%dT%H:%M:%SZ" )

echo "${DATE_S}: From $CLOUD $CLIENT_REGION to $SERVER_REGION ${BITRATE_HUMAN}B/sec and avg RTT $AVG_RTT" >>results.txt


aws ec2 terminate-instances --region $CLIENT_REGION --instance-ids $CLIENT_INSTANCE_ID

aws ec2 terminate-instances --region $SERVER_REGION --instance-ids $SERVER_INSTANCE_ID
