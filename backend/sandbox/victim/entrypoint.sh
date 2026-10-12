#!/bin/sh
# Serve a page for the client to browse, and run the sensor in the foreground.
set -e
nginx
exec python /app/sensor.py
