#!/bin/bash

#docker build --tag call518/deciflow-ui:0.0.1 .

docker run --detach \
  --name DeciFlow-UI \
  --hostname DeciFlow-UI \
  --init \
  --restart unless-stopped \
  --env DECIFLOW_DATA_DIR=/var/lib/deciflow-data \
  --publish 0.0.0.0:4000:4000 \
  --mount "type=bind,src=$(pwd),dst=/app,readonly" \
  --mount "type=volume,src=deciflow-venv,dst=/opt/deciflow-venv" \
  --mount "type=bind,src=/var/log,dst=/host-logs/var/log,readonly" \
  --mount "type=bind,src=$(pwd)/sample-logs,dst=/host-logs/sample-logs,readonly" \
  --mount "type=volume,src=deciflow-data,dst=/var/lib/deciflow-data" \
  --mount "type=volume,src=deciflow-logs,dst=/var/log/deciflow" \
  call518/deciflow-ui:0.0.1
