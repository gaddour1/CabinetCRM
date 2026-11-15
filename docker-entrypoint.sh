#!/bin/sh
set -eu

python manage.py check_migrations_safe
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
