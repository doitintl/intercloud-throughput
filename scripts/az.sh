#!/usr/bin/env bash
set -x
set -u
set -e

RESOURCE_GROUP=intercloud_rg
LOCATION=eastus
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
INIT_SCRIPT="az-install-and-run-iperf-server.sh"
FULLPATH_INIT_SCRIPT=$( realpath "$SCRIPT_DIR"/../startup-scripts/$INIT_SCRIPT)
VM_NAME=${LOCATION}-intercloud

az group create --name $RESOURCE_GROUP --location $LOCATION


CREATION_INFO=$( az vm create --resource-group $RESOURCE_GROUP --name $VM_NAME --image UbuntuLTS \
 --location $LOCATION \
 --custom-data $FULLPATH_INIT_SCRIPT \
 --generate-ssh-keys \
 --public-ip-sku Standard \
 --nic-delete-option delete \
 --os-disk-delete-option delete \
 --admin-username azureuser
 )

SERVER_ID=$( echo $CREATION_INFO |jq -r '.id' )
SERVER_IP=$( echo $CREATION_INFO |jq -r '.publicIpAddress' )

az vm open-port --id $SERVER_ID --port 5001

az vm run-command invoke --id $SERVER_ID --command-id RunShellScript \
 --scripts "echo runcommmand>>runcommand.txt"


#az vm delete -y --id $SERVER_ID