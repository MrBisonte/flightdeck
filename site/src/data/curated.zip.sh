#!/usr/bin/env bash
# One loader, one pipeline run. Every page reads from this archive, so the site
# cannot disagree with the pipeline about a number. The loader never writes SQL
# of its own: it runs the pipeline and ships what the pipeline published.
set -euo pipefail
cd "$(dirname "$0")/../../.."
./demo.sh build >&2
python - <<'PY'
import glob, io, os, sys, zipfile
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
    for path in sorted(glob.glob("warehouse/curated/*.parquet")):
        z.write(path, os.path.basename(path))
sys.stdout.buffer.write(buf.getvalue())
PY
