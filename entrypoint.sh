#!/bin/bash

mkdir -p /dev/net
mknod /dev/net/tun c 10 200 2> /dev/null
chmod 600 /dev/net/tun
JITStreamer $@