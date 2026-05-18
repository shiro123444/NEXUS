# FAST P2P Deployment

## Current Shape

Production uses two pieces:

- `apps/web`: static Vite build served by Nginx.
- `apps/relay`: Node WebSocket relay on `/ws` plus `/health`.

The recommended public layout is one HTTPS domain:

- `https://your-domain/` serves the web app.
- `wss://your-domain/ws` proxies to the relay.
- `https://your-domain/health` proxies to the relay health check.

With this layout the web app automatically derives the relay URL from the current origin, so `VITE_RELAY_URL` is not required.

## Docker Compose

From a fresh clone:

```bash
docker compose up -d --build
```

By default the app is exposed on host port `8080`.

```bash
WEB_PORT=80 docker compose up -d --build
```

For public TLS, put Caddy, Nginx Proxy Manager, Traefik, or a host-level Nginx in front of the compose web service and forward HTTPS traffic to `127.0.0.1:8080`.

## Direct Node + Nginx

Install dependencies and build:

```bash
npm ci
npm run install:apps
npm run build:apps
```

Start the relay:

```bash
HOST=127.0.0.1 PORT=3000 npm --prefix apps/relay run start
```

Serve `apps/web/dist` with Nginx and proxy `/ws` plus `/health` to `http://127.0.0.1:3000`.

Minimal Nginx location blocks:

```nginx
root /path/to/FAST-P2P/apps/web/dist;
index index.html;

location /health {
  proxy_pass http://127.0.0.1:3000/health;
}

location /ws {
  proxy_pass http://127.0.0.1:3000/ws;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_set_header Host $host;
  proxy_read_timeout 3600s;
  proxy_send_timeout 3600s;
}

location / {
  try_files $uri $uri/ /index.html;
}
```

## Preflight

Run this before deploying:

```bash
npm run deploy:check
```

After deployment:

```bash
curl -f https://your-domain/health
```

Then open two browser windows, create a room in one, join from the copied link in the other, and confirm both peers show connected.
