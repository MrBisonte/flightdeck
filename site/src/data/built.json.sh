#!/bin/sh
# The one loader that runs no SQL. It stamps when the site was built, so the
# page can show that clock beside the data clock the pipeline publishes. A fresh
# build over stale data looks current until you can see both.
set -eu
printf '{"built_at": "%s"}\n' "$(date -u '+%Y-%m-%d %H:%M')"
