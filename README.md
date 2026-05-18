# NEXUS — WBUAI Portal Infrastructure

Monorepo consolidating all services powering the **wbuai.me** ecosystem.

## Services

| Service | Path | Port | Description |
|---------|------|------|-------------|
| Portal Backend | `kiro-kroxy/` | 8080 | User portal + AI text-adventure game engine |
| CLI Proxy API | `cli-proxy-api/` | 8317 | OpenAI-compatible API management panel |
| Billing Gateway | `billing-gateway/` | 8300 | API usage billing & rate limiting |
| FAST-P2P | `fast-p2p/` | 3000 | P2P file transfer with WebSocket relay |
| MetaCubeXD Gateway | `metacubexd-gateway/` | 8094 | Clash dashboard proxy gateway |

## Domains

- `portal.wbuai.me` → Kiro-Kroxy (8080)
- `openai.wbuai.me` → CLI Proxy API + Billing (8317/8300)
- `p2p.wbuai.me` → FAST-P2P (3000)
- `edufish.wbuai.me` → External Cognitive AI service (3025)

## Configuration

- **Nginx**: `nginx/` — reverse proxy configs for all domains
- **Cloudflare**: `cloudflared/` — tunnel ingress rules
- **Systemd**: `systemd/` — service unit files

## Deployment

```bash
# Copy nginx configs
sudo cp nginx/*.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx

# Install systemd services
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Portal
sudo systemctl enable --now kiro-portal

# CLI Proxy Backend (binary required separately)
sudo systemctl enable --now cliproxy-api billing-gateway

# P2P Relay
sudo systemctl enable --now fast-p2p-relay
```

## Secrets

Never commit these files:
- `config.yaml` (use `config.example.yaml` as template)
- `*.pem`, `*.key` (SSL certificates)
- `.env`, `.env.*`
- Any file containing API keys
