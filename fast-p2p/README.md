# FAST-P2P

FAST-P2P is a small P2P experiment platform with a web client, a blind WebSocket relay, and shared protocol code for local TUI/Node experiments. The current focus is the foundation: secure session identity, transport interfaces, relay deployment, and an early AI-agent message layer.

It is not trying to be a full agent product yet. The agent layer is intentionally narrow: versioned messages, capability negotiation, encrypted signaling, and stable interfaces that future transports can reuse.

## What Runs

- `apps/web`: Vite web client for creating and joining transfer sessions.
- `apps/relay`: Node/Hono WebSocket relay with `/ws` and `/health`.
- `packages/shared`: session, transport, relay protocol, browser crypto, and agent protocol primitives.
- `example/p2p.ts`: local P2P/TUI-side experiment entry point.

Recommended public deployment uses one HTTPS origin:

- `https://your-domain/` serves the web app.
- `wss://your-domain/ws` proxies WebSocket relay traffic.
- `https://your-domain/health` checks the relay.

With that layout the web app derives the relay URL from the current page origin, so `VITE_RELAY_URL` is only needed for custom topologies.

## Security Model

The relay is designed to be blind to file contents and agent signal contents:

- `roomCode` is only a routing identifier for the relay.
- `sessionSecret` is generated client-side and used as key material.
- Invite links use `/?room=ROOM#key=SECRET`; the URL hash is not sent in HTTP requests.
- Manual join tokens use `ROOM SECRET`.
- File chunks are encrypted by peers before relay forwarding.
- Agent protocol messages can be wrapped as encrypted `agent/secure` signals.

The relay can still see metadata such as client IPs, room membership, connection timing, and message sizes. Treat it as a public rendezvous service, not as a trusted data processor.

For internet deployment:

- Put the web service behind HTTPS and use WSS for `/ws`.
- Expose only the reverse proxy or compose web port to the internet.
- Keep the relay bound inside Docker or to `127.0.0.1` when using host Nginx.
- Do not expose development servers directly.
- Add external rate limiting/firewall rules if you expect public traffic.

You do not need LAN-only connectivity when the server is public. Browsers connect to the public HTTPS/WSS endpoint; the relay only routes encrypted payloads between peers.

## Local Verification

From a fresh clone:

```bash
npm ci
npm run install:apps
npm run deploy:check
```

`npm run deploy:check` runs the test suite, builds the relay, and builds the web app.

Optional production dependency audits:

```bash
npm audit --omit=dev --prefix apps/web
npm audit --omit=dev --prefix apps/relay
```

## Docker Deployment

Docker Compose is the easiest server path:

```bash
docker compose up -d --build
```

By default the app is exposed on host port `8080`:

```bash
curl -f http://127.0.0.1:8080/health
```

To expose a different host port:

```bash
WEB_PORT=80 docker compose up -d --build
```

For public TLS, put Caddy, Nginx Proxy Manager, Traefik, or a host-level Nginx in front of the compose web service and forward HTTPS traffic to `127.0.0.1:8080`.

More detail is in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Direct Node + Nginx Deployment

Build everything:

```bash
npm ci
npm run install:apps
npm run build:apps
```

Start the relay on localhost:

```bash
HOST=127.0.0.1 PORT=3000 npm --prefix apps/relay run start
```

Then serve `apps/web/dist` with Nginx and proxy:

- `/ws` to `http://127.0.0.1:3000/ws`
- `/health` to `http://127.0.0.1:3000/health`
- all other routes to the static web app

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for a minimal Nginx config.

## P2P And Agent Foundation

The shared protocol layer currently provides:

- relay session splitting via `roomCode` and `sessionSecret`
- a transport abstraction for relay, LAN, swarm, or future WebRTC adapters
- relay protocol helpers for room lifecycle and encrypted file chunks
- agent protocol messages: `agent/hello`, `agent/accept`, `agent/reject`, and `agent/envelope`
- explicit capabilities such as `chat`, `file-transfer`, `tool-call`, `memory-sync`, `model-context`, and `consent-request`
- encrypted agent signal wrapping for the web relay path

This gives future AI-agent experiments a safe starting point without granting peers implicit tool or memory access. Capability advertisement is negotiation metadata only; product policy and user consent still need to be built above it.

## Local P2P Example

The local P2P demo in `example/p2p.ts` depends on `hyperswarm`.

```bash
npx --yes tsx ./example/p2p.ts
```

Bun currently does not support the required libuv API used by the native module, so use Node for this example.
