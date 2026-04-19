#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

pip install -r requirements.txt
python manage.py check --deploy
python manage.py collectstatic --no-input
