# Verified identity and backend workflows

The API defaults to `PORTWATCH_IDENTITY_MODE=verified`. Missing, invented, expired or revoked bearer sessions return 401. Unknown mode names also select verified mode. Client role, administrator, port, organisation and vessel headers cannot change a verified account's access: middleware replaces them before existing workflow routes resolve them.

Accounts, password hashes, memberships, session hashes and login throttles live in `PORTWATCH_AUTH_DB`, defaulting to `PORTWATCH_STATE_DIR/identity.db`. This implementation uses server-managed accounts; institutional OIDC/SSO is not connected. There are no shipped production accounts, public registration endpoint or default password.

## Configure an operator

Run on the API host with its Python environment and persistent state directory:

```powershell
$env:PORTWATCH_STATE_DIR = 'D:\PortWatchState'
$env:PORTWATCH_IDENTITY_MODE = 'verified'
python -m scripts.provision_identity --email controller@example.org --name 'JNPA Controller' --role PORT_AUTHORITY --port INNSA --organisation 'JNPA Authority'
```

The command prompts twice for a password; it does not accept passwords on the command line. Registered port codes are canonicalized. Repeat `--port` to assign more memberships. Reprovisioning changes server-owned membership and revokes all existing sessions. Provision national command separately with `--role NATIONAL_ADMIN` and omit `--port`. The host administrator controls this command and the identity database.

Build the terminal with `VITE_PORTWATCH_AUTH_MODE=production` (also the default). Set `VITE_PORTWATCH_API_BASE` for another API origin and restrict `PORTWATCH_CORS_REGEX` to the deployed terminal origin. Serve production traffic through HTTPS. Sign-in verifies credentials against the API, restoration rechecks the session, and logout revokes it. Production sessions use the browser tab's session storage; cached queries are cleared when identity changes.

Passwords use salted scrypt (`N=131072`, `r=8`, `p=1`), following [OWASP guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). Tokens contain 256 bits of randomness; only their SHA-256 digests are stored. Sessions expire after eight hours or thirty idle minutes, using wall time independently of replay. Sign-in attempts are limited over fifteen minutes by account and network address; forwarded client-IP headers are not trusted. Password hashing concurrency is bounded at two. These controls do not provide MFA or institutional identity assurance.

Explicit demo mode supports published demo roles for demonstration (`VITE_PORTWATCH_AUTH_MODE=demo`, `PORTWATCH_IDENTITY_MODE=asserted`). Private cameras are hidden from asserted users. Camera registration, evidence and weather observation writes require verified sessions in every mode. Proxy-required mode remains a legacy compatibility setting and receives a production readiness warning.

Private camera membership comes exclusively from the server account. National command may see all registered ports; a port authority sees its assigned ports. A feed URL does not replace the camera provider's own access controls. No private stream or real operator account was supplied or provisioned by this change.

## Replay and forecast availability

Camera evidence appears only when both `observedAt` and server-stamped `recordedAt` are no later than the replay instant. Legacy evidence without a recording timestamp is withheld. Current camera URLs are removed from historical/scenario responses; the UI also refuses playback. Registry metadata is labelled current because registration versions and media archives do not yet exist. Evidence and registry writes require the live clock.

`/api/intelligence/context?weatherVariable=wind_speed` selects the variable before the bounded result limit. Omit `portCode` for all thirteen ports. The feedback endpoint accepts `variable` and `limit`; `matchingForecasts` exposes truncation. The UI requests its selected variable from the server and identifies truncated history.

## Repeat real backend verification

The QA server creates isolated SQLite state under `work/verified-qa/`. Public credentials, weather values and camera registration are labelled test inputs. It serves the actual FastAPI app and decision/advisory engine; browser API responses are not mocked.

```powershell
python -m scripts.serve_verified_qa
# In the terminal project:
$env:NITRO_PRESET = 'node-server'
$env:VITE_PORTWATCH_AUTH_MODE = 'production'
$env:VITE_PORTWATCH_API_BASE = 'http://127.0.0.1:9281/api'
npm run build
$env:PW_SKIP_BUILD = '1'
$env:PW_REAL_API = 'http://127.0.0.1:9281/api'
npx playwright test qa/tests/verified-backend.spec.ts --project=laptop-1366 --project=desktop-1920 --workers=1
```

The suite verifies sign-in/restoration, all-port wind/wave selection, camera persistence, recorded-time replay exclusion and zero replay media requests. It also computes a port decision, reviews and approves an option, hands off draft advisories, issues through the controller's browser, and acknowledges through a separate verified company's browser. The persisted audit actor and decision-to-advisory link are checked through the real API. This proves the workflow on QA inputs, not operational savings or real camera health.

Include `identity.db`, `intelligence.db` and existing ledger/advisory stores in protected backups. Dependency locking and automated backup/restore drills remain separate readiness work.
