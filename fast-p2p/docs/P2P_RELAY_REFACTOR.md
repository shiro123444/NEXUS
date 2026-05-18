# P2P Relay Refactor

## Goal

Shift the current relay mode from "server-assisted encrypted transfer" toward a transport-agnostic P2P session model where:

- room codes are routing identifiers only
- session secrets are generated and kept client-side
- the relay can forward encrypted payloads without knowing the session key
- future transports can reuse the same session identity model

## First Slice

The first implementation slice keeps the existing relay transport and file transfer flow, but separates:

- `roomCode`: used by the relay to place peers into the same rendezvous room
- `sessionSecret`: used by peers to derive the encryption key

This gives us a blind relay fallback while staying compatible with legacy room-only joins.

## Session Model

- creator receives a relay room code from the server
- creator generates a local `sessionSecret`
- share link becomes `/?room=ROOM01#key=SECRET`
- manual join token becomes `ROOM01 SECRET`
- joiner derives encryption key from `sessionSecret`
- if no secret is provided, clients fall back to the legacy `roomCode -> key` mapping

## Why This Matters

- relay cannot derive the data key from the room code anymore
- the same invite model can later carry transport preferences, capabilities, or signed agent descriptors
- we can introduce WebRTC, Hyperswarm, or direct LAN transports without changing user-facing session semantics

## Next Phases

1. Extract a shared `Transport` interface for relay, LAN, and swarm transports.
2. Move session handshake messages out of app-specific UI code.
3. Add long-lived node identities and authenticated key exchange.
4. Introduce AI-agent protocol messages on top of the transport/session core.

## Agent Protocol Layer

The first agent protocol slice defines a versioned message family that can ride on any transport:

- `agent/hello`: peer identity, capabilities, and session offer
- `agent/accept`: negotiated capabilities for this session
- `agent/reject`: explicit missing capability or policy rejection
- `agent/envelope`: chat, tool calls, tool results, memory sync, model context, budget control, consent requests, or opaque payloads

Capabilities are intentionally explicit. A node can announce `chat`, `tool-call`, `memory-sync`, `model-context`, or other domain-specific features without implying that every peer may use them automatically.
