---
name: YouTube OAuth on headless Replit (Streamlit)
description: Why desktop OAuth fails on Replit and how the web-redirect flow must be built for a Streamlit app
---

# YouTube upload OAuth on headless Replit

- **Desktop `InstalledAppFlow.run_local_server()` CANNOT work on Replit.** It spawns a browser + local webserver on the *server*; the cloud machine is headless, so consent never completes. Must use the web-redirect `Flow` instead.
- Required user setup: OAuth client must be type **Web application** (not Desktop), with `https://<REPLIT_DOMAIN>/` registered as an Authorized redirect URI. `YOUTUBE_CLIENT_SECRETS_JSON` must hold the **full JSON file** (top-level `web` key) — users commonly paste just the bare `GOCSPX-...` client-secret string by mistake; detect & message that explicitly.
- **Streamlit-specific trap: the OAuth redirect lands in a BRAND-NEW Streamlit session.** Anything stashed in `st.session_state` before the redirect (e.g. anti-CSRF `state`) is GONE on return. Persist the `state` to a small file (with TTL + single-use consume), not session_state, or state validation will always fail.
- Callback pattern: read `st.query_params` for `code`/`state`/`error` at top of script, exchange, then `st.query_params.clear()` + `st.rerun()`. The clear() is what prevents re-trigger — do NOT add a `session_state` "done" flag, it silently blocks legitimate reconnects.
- Use `prompt=consent` + `access_type=offline` to force a refresh_token; warn the user if none is returned (uploads die after ~1h).
- Store creds as JSON (`Credentials.to_json` / `from_authorized_user_file`), not pickle — pickle of creds is an avoidable deserialization-RCE class.
- `redirect_uri` derives from `REPLIT_DOMAINS` (falls back to `REPLIT_DEV_DOMAIN`); it changes between dev and published, so both must be registered in Google Cloud.
- **In this pnpm-workspace repl the dev-domain ROOT `/` (externalPort 80) is owned by another service (mockup-sandbox), NOT the Streamlit app.** The Streamlit workflow is on container port 5000 and is reachable EXTERNALLY at `https://<domain>:5000/` — verified by external screenshot loading the full app, including a `?code=&state=` callback URL. So `redirect_uri()` must include `:5000` (provide a `YOUTUBE_OAUTH_REDIRECT_URI` override for the published domain, which serves at `/`).
- **`.replit` cannot be edited directly** (blocked: "Direct edits to .replit not allowed"). Port mappings/run commands are managed by dedicated tools (workflows skill etc.), and `configureWorkflow` supported ports do NOT include 80 — so you cannot just remap Streamlit onto the root. Don't try; the `:5000` URL works.
- A **502 on the OAuth return is usually transient** — Streamlit briefly unavailable while it hot-reloads after a code edit / workflow restart. If the redirect reached `:5000` and 502'd (vs. Google showing `redirect_uri_mismatch`), the URI is registered correctly; just retry once the app is stable.
