import { createRelayRooms } from "../src/p2p/relay-rooms"

const relayRooms = createRelayRooms<Bun.WebSocket<{ roomCode?: string; peerId?: string }>>()

Bun.serve<{ roomCode?: string; peerId?: string }>({
  port: Number(process.env.PORT ?? 8080),

  fetch(req, server) {
    const url = new URL(req.url)
    if (url.pathname === "/health") {
      return new Response("OK")
    }

    const success = server.upgrade(req, {
      data: { roomCode: undefined, peerId: undefined },
    })
    if (success) return undefined
    return new Response("WebSocket upgrade failed", { status: 500 })
  },

  websocket: {
    message(ws: Bun.WebSocket<{ roomCode?: string; peerId?: string }>, data: string | Buffer) {
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(data.toString())
      } catch {
        ws.send(JSON.stringify({ type: "error", message: "Invalid JSON" }))
        return
      }
      relayRooms.handleMessage(ws, msg)
    },

    close(ws: Bun.WebSocket<{ roomCode?: string; peerId?: string }>) {
      relayRooms.handleClose(ws)
    },
  },
})

console.log(`[Relay] Server running on port ${process.env.PORT ?? 8080}`)
