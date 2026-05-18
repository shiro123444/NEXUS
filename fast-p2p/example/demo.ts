import { TUI, RGBA, h, createTUI, getGlobalTUI } from "../src"
import * as os from "os"

const theme = {
  bg: RGBA.fromHex("#0d1117"),
  panel: RGBA.fromHex("#161b22"),
  border: RGBA.fromHex("#30363d"),
  primary: RGBA.fromHex("#58a6ff"),
  text: RGBA.fromHex("#c9d1d9"),
  textMuted: RGBA.fromHex("#8b949e"),
  accent: RGBA.fromHex("#3fb950"),
  error: RGBA.fromHex("#f85149"),
  warning: RGBA.fromHex("#d29922"),
  elem: RGBA.fromHex("#161b22"),
}

const tui = createTUI({ targetFps: 10, exitOnCtrlC: true })
tui.start()
tui.setBackground(theme.bg)

let selected = 0
let inputValue = ""
let viewMode: "home" | "connect" = "home"
let wsServer: { stop: () => void } | null = null
let peerConnected = false
let transferProgress = 0
let transferFile = ""
let serverPort = 3001

const menuItems = [
  { label: "New Session", action: () => {} },
  { label: "Open Project", action: () => {} },
  { label: "Settings", action: () => {} },
  { label: "Help", action: () => {} },
  { label: "Exit", action: () => tui.stop(0) },
]

function getLocalIP(): string {
  const nets = os.networkInterfaces()
  for (const name of Object.keys(nets)) {
    for (const net of nets[name] ?? []) {
      if (net.family === "IPv4" && !net.internal) {
        return net.address
      }
    }
  }
  return "127.0.0.1"
}

function genCode(len = 6): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  let code = ""
  for (let i = 0; i < len; i++) {
    code += chars[Math.floor(Math.random() * chars.length)]
  }
  return code
}

function generateQRCode(text: string): string[] {
  const SIZE = 21
  const qr: boolean[][] = Array.from({ length: SIZE }, () => Array(SIZE).fill(false))

  function setFinder(y: number, x: number) {
    for (let dy = 0; dy < 7; dy++) {
      for (let dx = 0; dx < 7; dx++) {
        const isEdge = dy === 0 || dy === 6 || dx === 0 || dx === 6
        const isInner = dy >= 2 && dy <= 4 && dx >= 2 && dx <= 4
        qr[y + dy][x + dx] = isEdge || isInner
      }
    }
  }

  setFinder(0, 0)
  setFinder(0, SIZE - 7)
  setFinder(SIZE - 7, 0)

  const bytes: number[] = []
  for (let i = 0; i < text.length; i++) {
    bytes.push(text.charCodeAt(i))
  }

  const bits: boolean[] = []
  bits.push(true)
  bits.push(false)
  bits.push(true)

  for (const b of bytes) {
    for (let i = 7; i >= 0; i--) {
      bits.push((b >> i) % 2 === 1)
    }
  }

  bits.push(false)

  while (bits.length < SIZE * SIZE * 0.4) {
    bits.push(bits.length % 2 === 0)
  }

  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      if (!qr[y][x] && bits.length > 0) {
        qr[y][x] = bits.shift() ?? false
      }
    }
  }

  const lines: string[] = []
  for (let y = 0; y < SIZE; y += 2) {
    let line1 = ""
    let line2 = ""
    for (let x = 0; x < SIZE; x++) {
      const top = qr[y][x]
      const bot = y + 1 < SIZE ? qr[y + 1][x] : false
      if (top && bot) {
        line1 += "█"
        line2 += "█"
      } else if (top && !bot) {
        line1 += "▀"
        line2 += " "
      } else if (!top && bot) {
        line1 += " "
        line2 += "▄"
      } else {
        line1 += " "
        line2 += " "
      }
    }
    lines.push(line1)
    if (y + 1 < SIZE) lines.push(line2)
  }

  return lines
}

async function startConnectMode() {
  viewMode = "connect"
  const roomCode = genCode()
  const ip = getLocalIP()
  serverPort = 3001
  const connectUrl = `ws://${ip}:${serverPort}/${roomCode}`

  console.log(`[Connect] Server: ${ip}:${serverPort}`)
  console.log(`[Connect] URL: ${connectUrl}`)

  const rooms = new Map<string, { creator: any; ws: any }>()

  try {
    const server = Bun.serve({
      port: serverPort,
      fetch(req, srv) {
        const url = new URL(req.url)
        if (url.pathname === "/health") return new Response("OK")
        const roomCodeFromPath = url.pathname.slice(1)
        const success = srv.upgrade(req, { data: { room: roomCodeFromPath } })
        if (success) return undefined
        return new Response("WebSocket upgrade failed", { status: 500 })
      },
      websocket: {
        open(ws: any) {
          const room = rooms.get(ws.data.room)
          if (room && !room.ws) {
            room.ws = ws
            peerConnected = true
            console.log("[Connect] Peer connected!")
          }
          rerender()
        },
        message(ws: any, data: any) {
          const room = rooms.get(ws.data.room)
          if (!room) return
          const target = ws === room.creator ? room.ws : room.creator
          if (target) target.send(data)
          try {
            const msg = JSON.parse(data)
            if (msg.type === "file_start") {
              transferFile = msg.filename
              transferProgress = 0
            } else if (msg.type === "file_chunk") {
              transferProgress = msg.progress
            } else if (msg.type === "file_done") {
              transferProgress = 1
              console.log("[Connect] Received:", transferFile)
            }
          } catch {}
          rerender()
        },
        close(ws: any) {
          const room = rooms.get(ws.data.room)
          if (room) {
            if (room.creator === ws) {
              room.ws?.close()
              rooms.delete(ws.data.room)
            } else {
              room.ws = null
              peerConnected = false
            }
          }
          rerender()
        },
      },
    })

    rooms.set(roomCode, { creator: null, ws: null })
    rooms.get(roomCode)!.creator = { send: () => {}, close: () => {} }

    wsServer = { stop: () => server.stop() }
  } catch (err) {
    console.error("[Connect] Server error:", err)
    viewMode = "home"
  }

  rerender()
}

function rerender() {
  const t = getGlobalTUI()
  if (t) t.renderElement(App())
}

function App() {
  const { width, height } = tui.getTerminalDimensions()
  if (viewMode === "connect") return ConnectView(width, height)
  return HomeView(width, height)
}

function HomeView(width: number, _height: number) {
  return h("box", {
    width,
    height: _height,
    backgroundColor: theme.bg,
    children: [
      HeaderBar(width),
      h("box", {
        flexDirection: "column",
        gap: 1,
        padding: 2,
        children: [
          h("text", { fg: theme.primary, children: "┌─────────────────────────────────────────┐" }),
          h("text", { fg: theme.primary, children: "│         TUI Framework Demo               │" }),
          h("text", { fg: theme.primary, children: "└─────────────────────────────────────────┘" }),
          h("text", { fg: theme.textMuted, children: `Terminal: ${width}x${_height}` }),
          h("text", { fg: theme.textMuted, children: "" }),
          ...menuItems.map((item, i) =>
            h("box", {
              backgroundColor: selected === i ? theme.elem : undefined,
              padding: 1,
              onClick: () => {
                selected = i
                item.action()
                rerender()
              },
              children: [
                h("text", { fg: selected === i ? theme.primary : theme.text, children: selected === i ? "▶ " : "  " }),
                h("text", { fg: selected === i ? theme.text : theme.textMuted, children: item.label }),
              ],
            }),
          ),
          h("text", { fg: theme.textMuted, children: "" }),
          h("box", {
            border: true,
            borderColor: theme.border,
            padding: 1,
            children: h("text", { fg: theme.text, children: "Input: " + inputValue + "_" }),
          }),
          h("text", { fg: theme.textMuted, children: "─".repeat(40) }),
          h("text", { fg: theme.accent, children: "💡 Type /connect to show QR code for file sharing" }),
        ],
      }),
    ],
  })
}

function ConnectView(width: number, _height: number) {
  const ip = getLocalIP()
  const url = `ws://${ip}:${serverPort}`
  const qrLines = generateQRCode(url)
  const roomCode = wsServer ? (Object.keys({}).find((k) => k) ?? "P2P") : ""

  return h("box", {
    width,
    height: _height,
    backgroundColor: theme.bg,
    children: [
      h("box", {
        width,
        height: 1,
        backgroundColor: theme.panel,
        children: [
          h("text", { fg: theme.textMuted, children: " " }),
          h("text", {
            fg: theme.primary,
            onClick: () => {
              viewMode = "home"
              wsServer?.stop()
              wsServer = null
              peerConnected = false
              rerender()
            },
            children: "← Back",
          }),
          h("text", { fg: theme.textMuted, children: " │ " }),
          h("text", {
            fg: peerConnected ? theme.accent : theme.warning,
            children: peerConnected ? "● Peer Connected" : "○ Waiting for scan...",
          }),
        ],
      }),
      h("box", {
        flexDirection: "column",
        gap: 1,
        padding: 2,
        children: [
          h("text", { fg: theme.primary, children: "┌─ LAN File Sharing ─────────────────────────┐" }),
          h("text", { fg: theme.text, children: "  Scan QR code with phone camera" }),
          h("text", { fg: theme.textMuted, children: `  Or open browser: http://${ip}:${serverPort}` }),
          h("text", { fg: theme.textMuted, children: "" }),
          ...qrLines.slice(0, 18).map((line) => h("text", { fg: theme.primary, children: "  " + line })),
          h("text", { fg: theme.textMuted, children: "" }),
          h("text", { fg: theme.accent, children: `  Port: ${serverPort}` }),
          h("text", { fg: theme.textMuted, children: "" }),
          h("text", { fg: theme.textMuted, children: "────────────────────────────────────────────" }),
        ],
      }),
    ],
  })
}

function HeaderBar(width: number) {
  return h("box", {
    width,
    height: 1,
    backgroundColor: theme.panel,
    children: h("text", {
      fg: theme.primary,
      children: " FAST P2P  │  ↑↓ Navigate  Enter Select  /connect  Esc Exit",
    }),
  })
}

tui.onKey((evt) => {
  if (evt.ctrl && evt.name === "c") {
    wsServer?.stop()
    tui.stop(0)
    return
  }

  if (evt.name === "escape") {
    if (viewMode === "connect") {
      viewMode = "home"
      wsServer?.stop()
      wsServer = null
      peerConnected = false
      rerender()
    }
    return
  }

  if (viewMode === "home") {
    if (evt.name === "up" || evt.name === "k") {
      selected = Math.max(0, selected - 1)
      rerender()
      return
    }
    if (evt.name === "down" || evt.name === "j") {
      selected = Math.min(menuItems.length - 1, selected + 1)
      rerender()
      return
    }
    if (evt.name === "return") {
      if (inputValue === "/connect") {
        void startConnectMode()
        inputValue = ""
        rerender()
        return
      }
      const action = menuItems[selected]?.action
      if (action) action()
      rerender()
      return
    }
    if (evt.name === "backspace") {
      inputValue = inputValue.slice(0, -1)
      rerender()
      return
    }
    if (evt.key && evt.key.length === 1 && !evt.ctrl && !evt.meta) {
      inputValue += evt.key
      if (inputValue === "/connect") {
        void startConnectMode()
        inputValue = ""
        rerender()
        return
      }
      rerender()
    }
  }
})

tui.renderElement(App())
console.log("\n[Demo] TUI P2P Demo")
console.log("[Demo] Type /connect + Enter to show QR code for LAN file sharing\n")
