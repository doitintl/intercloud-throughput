#!/bin/bash


apt-get install iperf
iperf -s
echo "Starting up" >>startup.txt
date >>startup.txt
