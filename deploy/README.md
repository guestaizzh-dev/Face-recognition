# Deployments

## Production

The production source of truth is the `zhengshi` branch. The FastAPI process runs on
`121.89.81.236`, listens only on `127.0.0.1:8005`, and is published by the existing
`faces.chbzg.com.cn` Nginx virtual host. The doctor login page remains
`https://chbzg.com/`; this deployment must not replace that site's `443` virtual host.

Production-specific files:

- `production.env.example`: settings for the `leda` production database (`chbzg`) and
  the same liveness/cooldown behavior currently verified in testing.
- `production-schema.sql`: manually reviewed migration for the three FastAPI state
  tables and `fa_doctor.face_verify_enabled`; the deployment scripts never run it.
- `face-verify.service`: the `8005` systemd unit for `/opt/face-verify-demo/current`.
- `leda-face_verify.php.example`: install as
  `/www/wwwroot/leda/config/face_verify.php`; the API key remains in the untracked
  `config/face_verify_api_key` file.
- `model-checksums.sha256`: exact anti-spoofing model hashes shared with testing.
- `verify-production.sh`: checks the local/public release SHA, readiness, model hashes,
  and the `https://chbzg.com` CORS preflight after deployment.

The filled production environment file stays outside the repository at
`/opt/face-verify-demo/shared/.env`. Both MySQL DSNs must use the production database
`chbzg` through a production-only SSH tunnel (the example uses local port `13306`),
never the testing database or its `13316` tunnel. Do not put database passwords,
internal API keys, or template encryption keys in Git.

The production database currently has the PHP event/profile/result tables but not the
three `fa_face_service_*` state tables or `fa_doctor.face_verify_enabled`. Back up the
database and manually execute `production-schema.sql` before enabling the new FastAPI
state store. `/api/ready` must report all configured schemas as healthy before traffic
is switched.

For every release, deploy an exact 40-character commit SHA into a new release
directory, set that same value in `/opt/face-verify-demo/shared/release.env` as
`FACE_DEMO_RELEASE_SHA=<sha>`, switch the `current` symlink, and restart only
`face-verify.service`. Then run:

```bash
sudo /opt/face-verify-demo/current/deploy/verify-production.sh <sha>
```

The GitHub workflow packages each `zhengshi` push as a commit-addressed archive,
publishes its SHA-256 checksum, and creates a GitHub build-provenance attestation.

## Testing

The test service listens on `127.0.0.1:19004`. After each doctor verification it writes the result to the existing `fa_face_verify_regulator_status` table and, when enabled, associates it with `fa_doctor_face_verify_log` through the DSN in `testing.env.example`; it does not modify other business tables. Nginx terminates HTTPS on the dedicated doctor face-verification port `9004` and proxies to `127.0.0.1:19004`. The existing business site on `443` is unchanged; only doctor login/verification responses should return a `verify_url` on port `9004`.

Before starting the service:

1. Install `requirements.txt` in the shared virtual environment.
2. Copy `testing.env.example` to the server's environment directory and replace every `CHANGE_ME` value.
3. Back up the SQLite state file and run `scripts/migrate_sqlite_state_to_mysql.py` before setting `FACE_DEMO_STATE_DB_DSN` for the first time.
4. Verify `/api/ready` reports the three `fa_face_service_*` state tables, both enabled result-table schemas and `ok: true`.
5. Run a failed verification and a passed verification against a test doctor, then correlate `fa_face_verify_regulator_status` and `fa_doctor_face_verify_log` by `business_event_id`.

The business login policy must keep `face_required=false` for non-doctor flows. For a doctor, after password verification, return the face session's `verify_url`, `session_id`, `upload_token`, actions and labels; the browser then uploads frames to port `9004` and completes the login proof through the existing business callback.

After the repository is deployed to `APP_ROOT`, run `sudo deploy/apply-testing.sh`. The script expects the filled `testing.env` file and an existing TLS certificate for `shualian.chbzg.com.cn`; it does not create or print secrets.
