#!/bin/sh
# Owner-authorized synthetic acceptance fixture. Does not upload or publish.
set -eu
ffmpeg -v error -f lavfi -i color=c=blue:s=720x900:r=30 \
  -f lavfi -i anullsrc=r=48000:cl=stereo -t 5 \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart "$1"
