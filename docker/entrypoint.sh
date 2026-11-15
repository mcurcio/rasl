#!/bin/sh
# Container entrypoint: set up the user, seed the config if it is missing, then run rasl.
#
# Environment (all optional):
#   PUID, PGID  The user and group rasl runs as when the container starts as root
#               (default 1000:1000). Ignored when it starts as another user (docker
#               --user, Kubernetes runAsUser): it then runs as that user.
#   UMASK       The umask for files rasl and the seed create (default 022).
#   TZ          The time zone (e.g. America/New_York); tzdata is in the image.
#   RASL_PORT   The web UI and API port of the default command and the health check
#               (default 8080).
#
# Started as root, it changes the owner of /config and everything in it to PUID:PGID
# (a failure, e.g. on root-squashed NFS, is reported and does not stop it), then runs
# itself again as PUID:PGID with no capabilities and no way to regain privileges, so
# rasl never runs as root (unless PUID is 0).
#
# Seeding writes SEED to CONFIG only when CONFIG does not exist, as the user rasl runs
# as, so a config already in the volume is never touched. It writes a temporary file and
# renames it into place, so rasl's watcher never reads a half-written file. If /config is
# not writable it warns and runs rasl anyway, which then reports the missing config.
#
# With no arguments it runs CONFIG with the web UI and API on RASL_PORT; arguments
# replace that and go to rasl.
set -eu

CONFIG=/config/rasl.conf
SEED=/usr/share/rasl/rasl.conf

log() {
    echo "rasl-entrypoint: $*" >&2
}

is_number() {
    case "$1" in
        '' | *[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

if [ "$(id -u)" = 0 ]; then
    PUID=${PUID:-1000}
    PGID=${PGID:-1000}
    is_number "$PUID" || { log "PUID must be a number, got '$PUID'"; exit 64; }
    is_number "$PGID" || { log "PGID must be a number, got '$PGID'"; exit 64; }
    if ! chown -R "$PUID:$PGID" /config 2>/dev/null; then
        log "could not change the owner of /config to $PUID:$PGID; carrying on"
    fi
    # Run this script again as PUID:PGID; RASL_DROPPED stops a loop if that is still root
    if [ -z "${RASL_DROPPED:-}" ]; then
        export RASL_DROPPED=1
        exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups \
            --inh-caps=-all --no-new-privs -- "$0" "$@"
    fi
elif [ -n "${PUID:-}${PGID:-}" ] && [ "${PUID:-$(id -u)}:${PGID:-$(id -g)}" != "$(id -u):$(id -g)" ]; then
    log "running as $(id -u):$(id -g); PUID and PGID apply only when the container starts as root"
fi

UMASK=${UMASK:-022}
case "$UMASK" in
    [0-7][0-7][0-7] | [0-7][0-7][0-7][0-7]) umask "$UMASK" ;;
    *) log "UMASK must be octal, like 022 or 0002, got '$UMASK'"; exit 64 ;;
esac

if [ ! -e "$CONFIG" ]; then
    tmp="$CONFIG.seed.$$"
    # A redirect, not cp: the new file's mode then follows UMASK
    if cat "$SEED" 2>/dev/null >"$tmp" && mv "$tmp" "$CONFIG"; then
        log "seeded $CONFIG with an empty graph"
    else
        rm -f "$tmp" 2>/dev/null || true
        log "$CONFIG is missing and could not be seeded (is /config writable by $(id -u):$(id -g)?)"
    fi
fi

if [ "$#" -eq 0 ]; then
    set -- "$CONFIG" --api-host 0.0.0.0 --api-port "${RASL_PORT:-8080}"
fi
exec rasl "$@"
