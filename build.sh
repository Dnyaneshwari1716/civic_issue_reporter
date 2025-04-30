#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

# Explicitly use pip
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python manage.py migrate
python manage.py collectstatic --noinput