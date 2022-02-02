#!/usr/bin/env bash

set -x
set -e
set -u

# The next line returns an error code and so this scripts returns an error code if
# 1. The region is not enabled
# 2. The global authentication endpoint is not configured to issue tokens for this region
aws ec2 describe-images \
  --region "$REGION" \
  --owners amazon \
  --filters 'Name=name,Values=amzn2-ami-hvm-2.0.????????-x86_64-gp2' 'Name=state,Values=available' \
  --output json
