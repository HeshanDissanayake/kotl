# Shared helpers for Kotl's deploy scripts. Source it; don't run it.
#
# Every script built on this supports:
#   --dry-run   change nothing: print each command, and write each file under a
#               temporary folder (or $KOTL_ROOT) so you can read exactly what would change
#   --undo      remove what the script added and restore any file it replaced
#
# Files Kotl writes start with a "managed by kotl" line. Before replacing a file that
# Kotl didn't write, the original is kept next to it as <file>.kotl-orig.

set -euo pipefail

KOTL_DRY_RUN=${KOTL_DRY_RUN:-0}
KOTL_ROOT=${KOTL_ROOT:-}
DEPLOY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MARK="managed by kotl"

say() { printf 'kotl-deploy: %s\n' "$*"; }
die() { printf 'kotl-deploy: error: %s\n' "$*" >&2; exit 1; }

# Call once, after option parsing.
start_mode() {
  if [ "$KOTL_DRY_RUN" = 1 ]; then
    if [ -z "$KOTL_ROOT" ]; then KOTL_ROOT=$(mktemp -d /tmp/kotl-dry-run.XXXXXX); fi
    say "dry run: nothing on this machine changes; files go under $KOTL_ROOT"
  elif [ "$(id -u)" != 0 ]; then
    die "run as root (sudo $0 ...), or add --dry-run to preview"
  fi
}

# run CMD...   runs it, or in a dry run just prints it
run() {
  if [ "$KOTL_DRY_RUN" = 1 ]; then printf 'would run: %s\n' "$*"; else "$@"; fi
}

# p /etc/x  ->  the real path, or the path under the dry-run folder
p() { printf '%s%s' "$KOTL_ROOT" "$1"; }

# put_file DEST MODE OWNER:GROUP   (content on stdin)
put_file() {
  local dest mode owner tmp
  dest=$(p "$1"); mode=$2; owner=$3
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ] && [ ! -e "$dest.kotl-orig" ] && ! grep -q "$MARK" "$dest" 2>/dev/null; then
    cp -p "$dest" "$dest.kotl-orig"
    say "kept the original as $1.kotl-orig"
  fi
  tmp=$(mktemp)
  cat >"$tmp"
  install -m "$mode" "$tmp" "$dest"
  rm -f "$tmp"
  if [ "$KOTL_DRY_RUN" != 1 ]; then chown "$owner" "$dest"; fi
  say "wrote $1 ($mode $owner)"
}

# remove_file DEST   restores DEST.kotl-orig if there is one, else deletes DEST
remove_file() {
  local dest
  dest=$(p "$1")
  if [ -e "$dest.kotl-orig" ]; then
    mv "$dest.kotl-orig" "$dest"; say "restored $1"
  elif [ -e "$dest" ]; then
    rm -f "$dest"; say "removed $1"
  fi
}

# make_dir PATH MODE OWNER:GROUP
make_dir() {
  local d
  d=$(p "$1")
  mkdir -p "$d"
  chmod "$2" "$d"
  if [ "$KOTL_DRY_RUN" != 1 ]; then chown "$3" "$d"; fi
  say "folder $1 ($2 $3)"
}

# set_conf FILE KEY VALUE   replaces "key = value" in a Kotl conf file (adds it if missing)
set_conf() {
  local f
  f=$(p "$1")
  [ -e "$f" ] || die "$1 is missing; run the install step first"
  if grep -q "^$2 *=" "$f"; then
    sed -i "s|^$2 *=.*|$2 = $3|" "$f"
  else
    printf '%s = %s\n' "$2" "$3" >>"$f"
  fi
  say "$1: $2 = $3"
}

# get_conf FILE KEY
get_conf() { { sed -n "s|^$2 *= *||p" "$(p "$1")" 2>/dev/null || true; } | head -n 1; }
