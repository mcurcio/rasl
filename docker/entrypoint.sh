#!/bin/sh
# Container entrypoint: seed the config if it is missing, then run rasl with the arguments.
#
# Seeding writes SEED (the image's starter config) to CONFIG only when CONFIG does not
# exist, so a config already in the volume is never touched. The copy goes to a temporary
# file first and is renamed into place, so rasl's watcher never reads a half-written file.
# The seeded file is mode 0666: the container runs as uid 65534 and owns it, and whoever
# edits it from outside (a NAS share, a bind mount) is usually another user. If the volume
# is not writable, it warns and runs rasl anyway, which then reports the missing config.
set -eu

CONFIG=/config/rasl.conf
SEED=/usr/share/rasl/rasl.conf

if [ ! -e "$CONFIG" ]; then
    tmp="$CONFIG.seed.$$"
    if cp "$SEED" "$tmp" 2>/dev/null && chmod 666 "$tmp" && mv "$tmp" "$CONFIG"; then
        echo "rasl-entrypoint: seeded $CONFIG with an empty graph" >&2
    else
        rm -f "$tmp" 2>/dev/null || true
        echo "rasl-entrypoint: $CONFIG is missing and could not be seeded (is /config writable?)" >&2
    fi
fi

exec rasl "$@"
