import { createServer as createHttpServer, type Server as HttpServer } from "node:http"
import { serve } from "@hono/node-server"
import { Hono } from "hono"
import { WebSocketServer, type WebSocket } from "ws"
import { createRelayRooms, type RelaySocketData } from "../../../src/p2p/relay-rooms.js"

type RelayWebSocket = WebSocket & {
  data: RelaySocketData
}

const port = Number(process.env.PORT ?? 3000)
const host = process.env.HOST ?? "0.0.0.0"
const app = new Hono()
const relayRooms = createRelayRooms<RelayWebSocket>()

app.get("/", (c) =>
  c.json({
    name: "PREACH relay",
    transport: "websocket",
    websocketPath: "/ws",
    health: "/health",
  }),
)

app.get("/health", (c) =>
  c.json({
    status: "ok",
    service: "relay",
  }),
)

const server = serve({
  createServer: createHttpServer,
  fetch: app.fetch,
  port,
  hostname: host,
}) as HttpServer

const wss = new WebSocketServer({ server, path: "/ws" })

wss.on("connection", (socket: WebSocket) => {
  const ws = socket as RelayWebSocket
  ws.data = { roomCode: undefined, peerId: undefined }

  ws.on("message", (raw: Buffer) => {
    let message: Record<string, unknown>
    try {
      message = JSON.parse(raw.toString())
    } catch {
      ws.send(JSON.stringify({ type: "error", message: "Invalid JSON" }))
      return
    }

    relayRooms.handleMessage(ws, message)
  })

  ws.on("close", () => {
    relayRooms.handleClose(ws)
  })
})

console.log(`[relay] listening on http://${host}:${port}`)
