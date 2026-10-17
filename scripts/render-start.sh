#!/bin/sh
set -eu
python backend/manage.py check --deploy --fail-level WARNING
# Free Render has no pre-deploy command. Run once before starting this instance.
# Only backwards-compatible migrations may be released this way.
python backend/manage.py migrate --noinput
exec gunicorn --chdir backend config.wsgi:application \
  --bind "0.0.0.0:${PORT:-10000}" --workers 1 --threads 4 --timeout 60 \
  --access-logfile - --access-logformat '%(m)s %(U)s %(s)s %(L)s' --error-logfile -
