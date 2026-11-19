#!/usr/bin/env bash
#
# A throwaway CA and a node certificate for an OpenSearch Service, for tests only:
# ca.crt, ca.key, tls.crt and a PKCS#8 tls.key in <dir>. helm-ci-fixtures.sh puts them in the
# Secret javv-ci-tls, and backend/tests/test_ci_certificates.py checks them.
#
#   development/scripts/make-test-certs.sh <dir> <service> <namespace>
#
# The CA carries basicConstraints and keyUsage: since Python 3.13, ssl.create_default_context()
# sets VERIFY_X509_STRICT, which refuses a CA without keyUsage (issue 1263). Requires openssl.
set -euo pipefail

dir=${1:?usage: make-test-certs.sh <dir> <service> <namespace>}
service=${2:?usage: make-test-certs.sh <dir> <service> <namespace>}
ns=${3:?usage: make-test-certs.sh <dir> <service> <namespace>}

openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=javv-ci-ca" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -keyout "$dir/ca.key" -out "$dir/ca.crt" 2>/dev/null
# genpkey writes PKCS#8, the only key format OpenSearch reads
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$dir/tls.key" 2>/dev/null
openssl req -new -key "$dir/tls.key" -subj "/CN=$service" -out "$dir/tls.csr"
cat > "$dir/ext" <<EOF
subjectAltName=DNS:$service,DNS:$service.$ns,DNS:$service.$ns.svc,DNS:$service.$ns.svc.cluster.local,DNS:$service-headless,DNS:localhost
extendedKeyUsage=serverAuth,clientAuth
keyUsage=digitalSignature,keyEncipherment
EOF
openssl x509 -req -in "$dir/tls.csr" -CA "$dir/ca.crt" -CAkey "$dir/ca.key" \
  -CAcreateserial -days 2 -extfile "$dir/ext" -out "$dir/tls.crt" 2>/dev/null
openssl verify -x509_strict -CAfile "$dir/ca.crt" "$dir/tls.crt" >/dev/null
