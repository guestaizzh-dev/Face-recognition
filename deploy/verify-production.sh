#!/usr/bin/env bash
set -euo pipefail

EXPECTED_SHA="${1:?usage: verify-production.sh <expected-40-character-git-sha>}"
APP_ROOT="${APP_ROOT:-/opt/face-verify-demo/current}"
MODEL_ROOT="${MODEL_ROOT:-/opt/face-verify-demo/shared/models}"
PYTHON_BIN="${PYTHON_BIN:-/opt/face-verify-demo/shared/.venv/bin/python}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://faces.chbzg.com.cn}"

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "Expected release SHA must be a full 40-character lowercase Git SHA." >&2
  exit 2
}

extract_release_sha() {
  "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["release_sha"])'
}

local_version="$(curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8005/api/version)"
local_sha="$(printf '%s' "$local_version" | extract_release_sha)"
test "$local_sha" = "$EXPECTED_SHA" || {
  echo "Local service SHA mismatch: expected $EXPECTED_SHA, got $local_sha" >&2
  exit 1
}

public_version="$(curl --fail --silent --show-error --max-time 15 "$PUBLIC_BASE_URL/api/version")"
public_sha="$(printf '%s' "$public_version" | extract_release_sha)"
test "$public_sha" = "$EXPECTED_SHA" || {
  echo "Public service SHA mismatch: expected $EXPECTED_SHA, got $public_sha" >&2
  exit 1
}

curl --fail --silent --show-error --max-time 30 http://127.0.0.1:8005/api/ready >/dev/null

(
  cd "$MODEL_ROOT"
  sha256sum --check "$APP_ROOT/deploy/model-checksums.sha256"
)

cors_headers="$(curl --silent --show-error --max-time 15 --dump-header - --output /dev/null \
  --request OPTIONS "$PUBLIC_BASE_URL/v1/verification-sessions/not-used/probe" \
  --header 'Origin: https://chbzg.com' \
  --header 'Access-Control-Request-Method: POST')"
printf '%s' "$cors_headers" | grep -qi '^access-control-allow-origin: https://chbzg.com' || {
  echo "Production CORS does not allow https://chbzg.com" >&2
  exit 1
}

echo "Production face service verified at release $EXPECTED_SHA on port 8005."
