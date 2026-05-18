import http, { type IncomingMessage, type ServerResponse } from "http"
import { WebSocketServer, type WebSocket } from "ws"

export interface LanPeer {
  send(data: string): void
  close(): void
}

export interface CreateLanServerOptions {
  port: number
  roomCode: string
  html: string
  onPeerConnected?: (peer: LanPeer) => void
  onPeerDisconnected?: () => void
  onMessage?: (message: any) => void
}

export interface LanServerHandle {
  port: number
  url: string
  wsBaseUrl: string
  stop(): Promise<void>
}

function writeHttp(res: ServerResponse, status: number, body: string, contentType = "text/plain"): void {
  res.writeHead(status, { "Content-Type": contentType })
  res.end(body)
}

export async function createLanServer(options: CreateLanServerOptions): Promise<LanServerHandle> {
  let activePeer: WebSocket | null = null
  let stopped = false

  const server = http.createServer((req: IncomingMessage, res: ServerResponse) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1")

    if (url.pathname === "/health") {
      writeHttp(res, 200, "OK")
      return
    }

    writeHttp(res, 200, options.html, "text/html; charset=utf-8")
  })

  const wss = new WebSocketServer({ noServer: true })

  wss.on("connection", (ws: WebSocket) => {
    if (activePeer && activePeer !== ws) {
      ws.close(1013, "Room full")
      return
    }

    activePeer = ws

    const peerHandle: LanPeer = {
      send(data: string) {
        if (ws.readyState === ws.OPEN) {
          ws.send(data)
        }
      },
      close() {
        ws.close()
      },
    }

    options.onPeerConnected?.(peerHandle)

    ws.on("message", (data) => {
      const text = typeof data === "string" ? data : data.toString()
      try {
        options.onMessage?.(JSON.parse(text))
      } catch {
        // Ignore malformed peer messages and keep the session alive.
      }
    })

    const handleDisconnect = () => {
      if (activePeer !== ws) return
      activePeer = null
      options.onPeerDisconnected?.()
    }

    ws.on("close", handleDisconnect)
    ws.on("error", handleDisconnect)
  })

  server.on("upgrade", (req, socket, head) => {
    if (stopped) {
      socket.destroy()
      return
    }

    const url = new URL(req.url ?? "/", "http://127.0.0.1")
    const roomCode = url.pathname.replace(/^\/+/, "")

    if (roomCode !== options.roomCode) {
      socket.write("HTTP/1.1 404 Not Found\r\n\r\n")
      socket.destroy()
      return
    }

    wss.handleUpgrade(req, socket, head, (ws) => {
      wss.emit("connection", ws, req)
    })
  })

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject)
    server.listen(options.port, "0.0.0.0", () => {
      server.off("error", reject)
      resolve()
    })
  })

  const address = server.address()
  if (!address || typeof address === "string") {
    throw new Error("Failed to resolve LAN server address")
  }

  const port = address.port

  return {
    port,
    url: `http://127.0.0.1:${port}`,
    wsBaseUrl: `ws://127.0.0.1:${port}`,
    async stop() {
      if (stopped) return
      stopped = true
      activePeer?.close()
      activePeer = null

      await new Promise<void>((resolve) => {
        wss.close(() => resolve())
      })

      await new Promise<void>((resolve, reject) => {
        server.close((err) => {
          if (err) {
            reject(err)
            return
          }
          resolve()
        })
      })
    },
  }
}
