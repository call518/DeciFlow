#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ( "$1" != up && "$1" != down ) ]]; then
  echo "Usage: $0 {up|down}" >&2
  exit 2
fi

project_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
: "${DECIFLOW_ENV_PATH:?Set DECIFLOW_ENV_PATH to your configuration file}"
configuration_file="$DECIFLOW_ENV_PATH"

if [[ "$configuration_file" == '~/'* ]]; then
  configuration_file="$HOME/${configuration_file:2}"
fi

if [[ ! -f "$configuration_file" ]]; then
  echo "Configuration file not found: $configuration_file. Run deciflow init first." >&2
  exit 1
fi

configuration_file="$(cd -- "$(dirname -- "$configuration_file")" && pwd)/$(basename -- "$configuration_file")"
export DECIFLOW_ENV_PATH="$configuration_file"

compose_args=(--project-directory "$project_directory" -f "$project_directory/docker-compose.yml" --env-file "$configuration_file")
if [[ "$1" == up ]]; then
  exec docker compose "${compose_args[@]}" up -d --remove-orphans
fi
exec docker compose "${compose_args[@]}" down
