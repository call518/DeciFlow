#!/bin/bash

#git clone --branch v0.4.1 --depth 1 https://github.com/NandhaKishorM/laya.git
#cd laya
#docker build --build-arg TORCH_INDEX=cu130 --tag call518/deciflow-laya:cuda .


docker run --detach \
  --name DeciFlow-Laya \
  --hostname DeciFlow-Laya \
  --init \
  --restart unless-stopped \
  --gpus all \
  --publish 0.0.0.0:8000:8000 \
  --volume deciflow-laya-model-cache:/home/laya/.cache/huggingface \
  --env LAYA_HOST=0.0.0.0 \
  --env LAYA_PORT=8000 \
  --env LAYA_DEVICE=cuda \
  --env LAYA_PRELOAD=1 \
  --env LAYA_MODELS=english,multilingual,typed-decisions \
  --env LAYA_API_KEY=changeme \
  call518/deciflow-laya-cuda:0.0.1 laya-serve
