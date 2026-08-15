# Deployment layouts

The repository has two deployment branches:

- `production`: formal environment, port `9003`, `https://cd.chbzg.com.cn`
- `testing`: test environment, port `9004`, `https://shualian.chbzg.com.cn`

The systemd units in this directory assume the shared layout documented in the root README. Copy the matching `*.env.example` file to the server, replace all `CHANGE_ME` values, install the matching unit, and put an HTTPS reverse proxy in front of the local port.

The doctor login and twice-daily random verification flow is a business-system integration. See [DOCTOR_FACE_VERIFICATION.md](DOCTOR_FACE_VERIFICATION.md) for the required API sequence and idempotency rules.
