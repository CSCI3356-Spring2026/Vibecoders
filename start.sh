#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

python manage.py migrate --noinput
exec daphne -b 0.0.0.0 -p "${PORT:?PORT is required}" vibecoders.asgi:application
