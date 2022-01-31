#!/usr/bin/env bash

set -x
set -e
set -u

# Just tests for regions that do not support the latest token format https://bobcares.com/blog/aws-was-not-able-to-validate-the-provided-access-credentials-how-to-fix/
aws ec2 describe-images \
  --region $REGION \
  --owners amazon \
  --filters 'Name=name,Values=amzn2-ami-hvm-2.0.????????-x86_64-gp2' 'Name=state,Values=available' \
  --output json
