#!/bin/sh
# Ordinary page loads with random think time, so the sensor always sees some normal traffic.
TARGET="${TARGET:-http://victim}"
while true; do
  curl -s -o /dev/null "$TARGET/" || true
  curl -s -o /dev/null "$TARGET/index.html" || true
  sleep "$(awk 'BEGIN{srand(); printf "%.1f", 0.5 + rand()*3}')"
done
