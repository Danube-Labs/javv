#!/bin/sh
#
# Makes .env for a new compose install of JAVV (issue 869): random secrets in place of the four
# empty ones in .env.example, and the first admin password shown one time. Run it once, in the
# folder of compose.yaml, before the first `docker compose up -d`.
#
#   ./setup.sh           browsers use plain http, for example http://<this machine>:8080
#   ./setup.sh --https   browsers use https://, through a proxy or a load balancer
#
# It never replaces an .env that exists: a new JAVV_SECRET_KEY ends every token and session.
set -eu

cd "$(dirname "$0")"

https=false
case "${1:-}" in
  "") ;;
  --https) https=true ;;
  -h | --help)
    sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'
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

# hex only: compose takes each value as it is, with no `$`, `#`, quote or space to rewrite
random_hex() {
  od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'
}

secret_key=$(random_hex 32)
admin_password=$(random_hex 12)
# OpenSearch wants an upper-case letter, a lower-case letter, a digit and a special character
opensearch_admin_password="Javv-$(random_hex 16)-0"
opensearch_password=$(random_hex 24)

# the template must have each line that this script fills, once, or the install is half made
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
