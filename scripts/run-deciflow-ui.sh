#!/bin/bash

#docker build --tag call518/deciflow-ui:0.0.1 .

docker run --detach \
  --name DeciFlow-UI \
  --init \
  --restart unless-stopped \
  --env-file .env \
  --publish 0.0.0.0:4000:4000 \
  --mount "type=bind,src=$(pwd),dst=/app,readonly" \
  --mount type=volume,src=deciflow-venv,dst=/opt/deciflow-venv \
  --mount type=bind,src=/var/log,dst=/host-logs,readonly \
  call518/deciflow-ui:0.0.1
