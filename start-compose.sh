#!/bin/sh
set -eu

docker compose up --build --detach
binding=$(docker compose port assurebench 8765)
port=${binding##*:}
printf 'AssureBench is starting at http://127.0.0.1:%s/\n' "$port"
