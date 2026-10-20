#!/bin/sh
#
# Makes .env for a new compose install of JAVV: random secrets in place of the four empty ones
# in .env.example, and the first admin password shown one time. Run it once, in the
# folder of compose.yaml, before the first `docker compose up -d`.
#
#   ./setup.sh           .env turns off the cookie's Secure flag, so sign-in works over http
#   ./setup.sh --https   .env keeps the cookie's Secure flag: the browser sends it only over https
#
# Use --https only when people open JAVV at an https:// address, through a proxy or a load
# balancer in front of JAVV. JAVV itself serves only http.
#
# A second install on this machine needs its own name: COMPOSE_PROJECT_NAME=<name> ./setup.sh.
# The script writes the name to .env. It stops if a volume of that name exists already.
#
# It never replaces an .env that exists: a new JAVV_SECRET_KEY makes every token and session
# invalid.
set -eu

cd "$(dirname "$0")"

https=false
case "${1:-}" in
  "") ;;
  --https) https=true ;;
  -h | --help)
    sed -n '3,17p' "$(basename "$0")" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    echo "setup.sh: unknown option '$1'. Use --https, or no option for plain http." >&2
    exit 2
    ;;
esac

if [ -e .env ]; then
  echo "setup.sh: .env exists. Nothing changed. To start again, move .env away first." >&2
  exit 1
fi
if [ ! -f .env.example ]; then
  echo "setup.sh: .env.example is missing. Put it next to compose.yaml, from the same release." >&2
  exit 1
fi

# compose names the volumes after the project: COMPOSE_PROJECT_NAME, else `name: javv` in
# compose.yaml. OpenSearch keeps the passwords of its first start, so a new .env cannot start on
# the volume of an earlier install: its health check gets 401.
project=${COMPOSE_PROJECT_NAME:-javv}
case $project in
  -* | _*) bad_name=true ;;
  *) bad_name=false ;;
esac
if [ "$bad_name" = true ] || [ -n "$(printf '%s' "$project" | LC_ALL=C tr -d 'a-z0-9_-')" ]; then
  echo "setup.sh: '$project' is not a project name for compose. Nothing changed." >&2
  echo "Use lower-case letters, digits, '-' and '_', and start with a letter or a digit." >&2
  exit 2
fi
volume="${project}_opensearch-data"
if command -v docker > /dev/null 2>&1 && docker volume inspect "$volume" > /dev/null 2>&1; then
  cat >&2 <<EOF
setup.sh: the volume $volume exists. Nothing changed.
It holds an earlier install of JAVV. OpenSearch keeps the passwords of that install, and it would
refuse the new ones. Do one of these:
- Delete the earlier install and its data, in this folder: docker compose down -v
- Keep it, and make a second install: COMPOSE_PROJECT_NAME=<new name> ./setup.sh
EOF
  exit 1
fi

# hex only: compose takes each value as it is, with no `$`, `#`, quote or space to rewrite
random_hex() {
  od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'
}

secret_key=$(random_hex 32)
admin_password=$(random_hex 12)
# OpenSearch wants an upper-case letter, a lower-case letter, a digit and a special character
opensearch_admin_password="Javv-$(random_hex 16)-0"
opensearch_password=$(random_hex 24)

# the template must have each line that this script fills, one time. If not, nothing changes
for line in JAVV_SECRET_KEY= JAVV_BOOTSTRAP_ADMIN_PASSWORD= JAVV_OPENSEARCH_ADMIN_PASSWORD= \
  JAVV_OPENSEARCH_PASSWORD= JAVV_SESSION_COOKIE_SECURE=false; do
  if [ "$(grep -c -x -- "$line" .env.example)" != 1 ]; then
    echo "setup.sh: .env.example has no single '$line' line (key ${line%%=*}). Nothing changed." >&2
    exit 1
  fi
done

umask 077
tmp=$(mktemp .env.XXXXXX)
trap 'rm -f "$tmp"' EXIT
awk -v https="$https" \
  -v secret_key="$secret_key" \
  -v admin_password="$admin_password" \
  -v opensearch_admin_password="$opensearch_admin_password" \
  -v opensearch_password="$opensearch_password" '
  $0 == "JAVV_SECRET_KEY=" { print $0 secret_key; next }
  $0 == "JAVV_BOOTSTRAP_ADMIN_PASSWORD=" { print $0 admin_password; next }
  $0 == "JAVV_OPENSEARCH_ADMIN_PASSWORD=" { print $0 opensearch_admin_password; next }
  $0 == "JAVV_OPENSEARCH_PASSWORD=" { print $0 opensearch_password; next }
  $0 == "JAVV_SESSION_COOKIE_SECURE=false" && https == "true" { next }
  { print }
' .env.example > "$tmp"
if [ -n "${COMPOSE_PROJECT_NAME:-}" ]; then
  printf 'COMPOSE_PROJECT_NAME=%s\n' "$project" >> "$tmp"
fi
chmod 600 "$tmp"
mv "$tmp" .env
trap - EXIT

if [ "$https" = true ]; then
  cookie="https: the session cookie is Secure"
else
  cookie="plain http (JAVV_SESSION_COOKIE_SECURE=false). Behind https, run ./setup.sh --https on a new .env"
fi
cat <<EOF
.env is ready, with random secrets. Only you can read it.

Sign in as admin with this password. JAVV asks you for a new one at the first sign-in:

    $admin_password

This script does not show it again. Until the first sign-in, it is also in .env
(JAVV_BOOTSTRAP_ADMIN_PASSWORD). Keep .env for the life of this install.

Browsers: $cookie.
Next: docker compose up -d
EOF

max_map_count_file=/proc/sys/vm/max_map_count
if [ -r "$max_map_count_file" ] && [ "$(cat "$max_map_count_file")" -lt 262144 ]; then
  echo "OpenSearch needs a larger memory map limit on this host. Run, one time:" >&2
  echo "    sudo sysctl -w vm.max_map_count=262144" >&2
fi
