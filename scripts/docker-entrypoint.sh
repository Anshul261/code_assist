#!/bin/sh
set -eu

: "${LANGGRAPH_SANDBOX_DIR:=/data/lg_workspace}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "${LANGGRAPH_SANDBOX_DIR}" /data/tmp
    chown app:app /data
    chown -R app:app "${LANGGRAPH_SANDBOX_DIR}" /data/tmp
    chmod 0750 /data "${LANGGRAPH_SANDBOX_DIR}"
    chmod 0700 /data/tmp
    export TMPDIR=/data/tmp
    exec gosu app:app "$@"
fi

if [ ! -w "${LANGGRAPH_SANDBOX_DIR}" ]; then
    echo "Storage is not writable by the unprivileged app user. On Railway with a volume, set RAILWAY_RUN_UID=0 so the entrypoint can initialize /data and then drop privileges." >&2
    exit 1
fi

exec "$@"
