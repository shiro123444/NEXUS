import type { ServerWebSocket } from "bun"

const PORT = Number(process.env.PORT ?? 3000)

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FAST P2P Relay</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:20px}
    h1{color:#58a6ff;margin-bottom:4px}
    .sub{color:#8b949e;margin-bottom:24px;font-size:.9em}
    .panel{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;width:100%;max-width:420px;margin-bottom:16px}
    .status{display:flex;align-items:center;gap:8px;margin-bottom:16px}
    .dot{width:10px;height:10px;border-radius:50%;background:#484f58}
    .dot.online{background:#3fb950}
    .dot.waiting{background:#d29922;animation:pulse 1s infinite}
    .dot.offline{background:#f85149}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    .room-code{font-size:2.2em;font-weight:bold;color:#58a6ff;letter-spacing:4px;font-family:monospace;text-align:center;margin:12px 0;word-break:break-all}
    .btn{width:100%;padding:12px;border:none;border-radius:6px;font-size:1em;cursor:pointer;transition:all .2s;margin-bottom:8px}
    .btn-primary{background:#238636;color:#fff}
    .btn-primary:hover{background:#2ea043}
    .btn-secondary{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
    .btn-secondary:hover{background:#30363d}
    .btn:disabled{opacity:.5;cursor:not-allowed}
    .transfer-area,.scan-area{border:2px dashed #30363d;border-radius:8px;padding:24px;text-align:center;cursor:pointer;transition:all .2s}
    .transfer-area{margin-top:8px}
    .transfer-area:hover,.scan-area:hover{border-color:#58a6ff}
    .transfer-area.dragover{border-color:#58a6ff;background:rgba(88,166,255,.1)}
    .hint{color:#8b949e;font-size:.9em;margin-top:8px}
    #fileInput{display:none}
    .progress-bar{height:8px;background:#21262d;border-radius:4px;overflow:hidden;margin-top:12px}
    .progress-fill{height:100%;background:#58a6ff;transition:width .2s;width:0}
    .progress-text{margin-top:6px;font-size:.85em;color:#8b949e;text-align:center}
    .file-list{margin-top:16px}
    .file-item{display:flex;align-items:center;gap:8px;padding:8px;background:#0d1117;border-radius:4px;margin-bottom:4px;font-size:.9em}
    .file-icon{width:24px;color:#3fb950}
    .file-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .file-size{color:#8b949e}
    .input{width:100%;padding:10px;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#c9d1d9;font-size:1em;text-align:center;text-transform:uppercase;letter-spacing:2px}
    .hidden{display:none!important}
    .logs{margin-top:16px;max-height:120px;overflow-y:auto;width:100%;max-width:420px;font-family:monospace;font-size:.82em}
    .log{color:#8b949e;padding:2px 0}
    #qrcode{display:flex;justify-content:center;margin:12px 0;min-height:180px}
    #qrcode canvas{border-radius:4px;background:#fff;padding:8px}
  </style>
</head>
<body>
  <h1>FAST P2P</h1>
  <p class="sub">Encrypted relay file transfer in the browser.</p>

  <div class="panel">
    <div class="status">
      <div class="dot waiting" id="dot"></div>
      <span id="statusText">Connecting to relay server...</span>
    </div>

    <div id="roomInfo" class="hidden">
      <div style="text-align:center;color:#8b949e">Room code</div>
      <div class="room-code" id="roomCode"></div>
      <div id="qrcode"></div>
      <div class="hint" id="roomHint"></div>
    </div>

    <div id="joinArea">
      <div class="scan-area" id="scanBtn">
        <div>Open this page on another device and scan the QR code there.</div>
        <div class="hint">Or enter a room code manually below.</div>
      </div>
      <input class="input" id="manualCode" placeholder="ENTER ROOM CODE">
      <button class="btn btn-primary" id="joinBtn">Join Room</button>
    </div>

    <button class="btn btn-secondary" id="createBtn">Create Room</button>
  </div>

  <div class="panel hidden" id="sendPanel">
    <div class="transfer-area" id="dropZone">
      <div>Click or drop a file to send.</div>
      <div class="hint">Files are encrypted before relay transport.</div>
    </div>
    <input type="file" id="fileInput">
    <div id="sendProgress" class="hidden">
      <div class="progress-bar"><div class="progress-fill" id="sendFill"></div></div>
      <div class="progress-text" id="sendProgressText"></div>
    </div>
    <div class="file-list" id="sendList"></div>
  </div>

  <div class="panel hidden" id="recvPanel">
    <div style="text-align:center;padding:20px 0">
      <div>Waiting for a file...</div>
    </div>
    <div id="recvProgress" class="hidden">
      <div class="progress-bar"><div class="progress-fill" id="recvFill"></div></div>
      <div class="progress-text" id="recvProgressText"></div>
    </div>
    <div class="file-list" id="recvList"></div>
  </div>

  <div class="logs" id="logs"></div>

  <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"></script>
  <script>
    const RELAY_URL = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host
    const CHUNK_SIZE = 32 * 1024

    let ws = null
    let room = null
    let peerId = null
    let peer = null
    let encKey = null
    let isCreator = false
    let isConnected = false
    let pendingFile = null

    const sentFiles = []
    const receivedFiles = []

    const $ = id => document.getElementById(id)
    const dot = $('dot')
    const statusText = $('statusText')
    const roomInfo = $('roomInfo')
    const roomCodeEl = $('roomCode')
    const roomHint = $('roomHint')
    const joinArea = $('joinArea')
    const createBtn = $('createBtn')
    const joinBtn = $('joinBtn')
    const scanBtn = $('scanBtn')
    const manualCode = $('manualCode')
    const sendPanel = $('sendPanel')
    const recvPanel = $('recvPanel')
    const dropZone = $('dropZone')
    const fileInput = $('fileInput')
    const sendProgress = $('sendProgress')
    const recvProgress = $('recvProgress')
    const sendFill = $('sendFill')
    const sendProgressText = $('sendProgressText')
    const recvFill = $('recvFill')
    const recvProgressText = $('recvProgressText')
    const sendList = $('sendList')
    const recvList = $('recvList')
    const qrcode = $('qrcode')
    const logsEl = $('logs')

    function log(msg) {
      const t = new Date().toLocaleTimeString('en-US', { hour12: false })
      const e = document.createElement('div')
      e.className = 'log'
      e.textContent = t + ' ' + msg
      logsEl.prepend(e)
    }

    function setStatus(text, state) {
      statusText.textContent = text
      dot.className = 'dot ' + state
    }

    function formatBytes(size) {
      if (size < 1024) return size + 'B'
      if (size < 1024 * 1024) return (size / 1024).toFixed(1) + 'KB'
      if (size < 1024 * 1024 * 1024) return (size / (1024 * 1024)).toFixed(1) + 'MB'
      return (size / (1024 * 1024 * 1024)).toFixed(1) + 'GB'
    }

    function addFile(list, name, size, status, target) {
      list.unshift({ name, size, status })
      target.innerHTML = list
        .map(file => '<div class="file-item"><span class="file-icon">' + (file.status === 'done' ? '[OK]' : '[..]') + '</span><span class="file-name">' + file.name + '</span><span class="file-size">' + formatBytes(file.size) + '</span></div>')
        .join('')
    }

    function showRoom(code, hint) {
      roomCodeEl.textContent = code
      roomHint.textContent = hint || 'Share this code or QR with the other device.'
      roomInfo.classList.remove('hidden')
      joinArea.classList.add('hidden')
      createBtn.classList.add('hidden')
      qrcode.innerHTML = ''
      QRCode.toCanvas(document.createElement('canvas'), location.origin + '?code=' + code, { width: 180 }, (err, canvas) => {
        if (!err) qrcode.appendChild(canvas)
      })
    }

    async function deriveKey(code) {
      const enc = new TextEncoder()
      const keyMaterial = await crypto.subtle.importKey('raw', enc.encode(code), 'PBKDF2', false, ['deriveBits'])
      const rawKey = await crypto.subtle.deriveBits(
        { name: 'PBKDF2', salt: enc.encode('fastp2p-salt'), iterations: 100000, hash: 'SHA-256' },
        keyMaterial,
        256,
      )
      return crypto.subtle.importKey('raw', rawKey, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'])
    }

    async function encrypt(data, key) {
      const iv = crypto.getRandomValues(new Uint8Array(12))
      const cipherText = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, data)
      return {
        iv: btoa(String.fromCharCode(...iv)),
        data: btoa(String.fromCharCode(...new Uint8Array(cipherText))),
      }
    }

    async function decrypt(payload, key) {
      const iv = new Uint8Array(atob(payload.iv).split('').map(char => char.charCodeAt(0)))
      const cipherText = new Uint8Array(atob(payload.data).split('').map(char => char.charCodeAt(0)))
      return new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipherText))
    }

    function connect() {
      ws = new WebSocket(RELAY_URL)

      ws.onopen = () => {
        isConnected = true
        setStatus('Connected to relay server', 'online')
        log('Connected to relay server')
        if (room && !isCreator) ws.send(JSON.stringify({ type: 'join', room }))
      }

      ws.onclose = () => {
        isConnected = false
        peer = null
        sendPanel.classList.add('hidden')
        setStatus('Relay disconnected. Retrying...', 'offline')
        log('Relay connection closed')
        setTimeout(connect, 2000)
      }

      ws.onerror = () => log('Relay connection error')

      ws.onmessage = async event => {
        let msg
        try {
          msg = JSON.parse(event.data)
        } catch {
          return
        }

        switch (msg.type) {
          case 'created':
            room = msg.room
            peerId = msg.peerId
            isCreator = true
            encKey = await deriveKey(room)
            showRoom(room, 'Share this room with the receiving device.')
            setStatus('Waiting for a peer to join', 'waiting')
            recvPanel.classList.add('hidden')
            log('Room created: ' + room)
            break

          case 'joined':
            room = msg.room
            peerId = msg.peerId
            isCreator = false
            encKey = await deriveKey(room)
            showRoom(room, 'Joined room. Waiting for incoming files.')
            recvPanel.classList.remove('hidden')
            setStatus('Connected to room', 'online')
            log('Joined room: ' + room)
            break

          case 'peer_joined':
            peer = msg.peerId
            recvPanel.classList.add('hidden')
            sendPanel.classList.remove('hidden')
            setStatus('Peer connected', 'online')
            log('Peer joined: ' + msg.peerId)
            break

          case 'peer_leave':
            peer = null
            sendPanel.classList.add('hidden')
            recvPanel.classList.remove('hidden')
            setStatus('Waiting for a peer to join', 'waiting')
            log('Peer left the room')
            break

          case 'relay':
            if (!encKey) return
            try {
              const chunk = await decrypt(msg.data, encKey)
              if (!pendingFile && msg.data._meta) {
                pendingFile = {
                  name: msg.data._meta.name,
                  size: msg.data._meta.size,
                  total: msg.data._meta.total,
                  received: 0,
                  chunks: [],
                }
              }
              if (!pendingFile) return
              pendingFile.chunks[msg.data.index] = chunk
              pendingFile.received += 1

              const pct = Math.round((pendingFile.received / pendingFile.total) * 100)
              recvFill.style.width = pct + '%'
              recvProgressText.textContent = pct + '% - ' + pendingFile.name
              recvProgress.classList.remove('hidden')

              if (pendingFile.received === pendingFile.total) {
                const blob = new Blob(pendingFile.chunks)
                const downloadLink = document.createElement('a')
                downloadLink.href = URL.createObjectURL(blob)
                downloadLink.download = pendingFile.name
                downloadLink.click()
                URL.revokeObjectURL(downloadLink.href)
                addFile(receivedFiles, pendingFile.name, pendingFile.size, 'done', recvList)
                log('Received: ' + pendingFile.name)
                pendingFile = null
                recvProgress.classList.add('hidden')
              }
            } catch {
              log('Failed to decrypt incoming chunk')
            }
            break

          case 'done':
            log('Transfer complete')
            break

          case 'error':
            log('Error: ' + msg.message)
            break
        }
      }
    }

    async function sendFile(file) {
      if (!peer) {
        log('Waiting for a peer connection before sending')
        return
      }
      if (!encKey) {
        log('Encryption key is not ready yet')
        return
      }

      const totalChunks = Math.ceil(file.size / CHUNK_SIZE)
      let sentCount = 0
      const buffer = await file.arrayBuffer()

      addFile(sentFiles, file.name, file.size, 'sending', sendList)
      sendProgress.classList.remove('hidden')

      for (let offset = 0, index = 0; offset < buffer.byteLength; offset += CHUNK_SIZE, index += 1) {
        const chunk = buffer.slice(offset, Math.min(offset + CHUNK_SIZE, buffer.byteLength))
        const payload = await encrypt(chunk, encKey)
        ws.send(
          JSON.stringify({
            type: 'relay',
            data: {
              ...payload,
              index,
              total: totalChunks,
              _meta: index === 0 ? { name: file.name, size: file.size, total: totalChunks } : null,
            },
          }),
        )
        sentCount += 1
        const pct = Math.round((sentCount / totalChunks) * 100)
        sendFill.style.width = pct + '%'
        sendProgressText.textContent = pct + '% - ' + file.name
        await new Promise(resolve => setTimeout(resolve, 5))
      }

      ws.send(JSON.stringify({ type: 'done' }))
      addFile(sentFiles, file.name, file.size, 'done', sendList)
      sendProgress.classList.add('hidden')
      log('Sent: ' + file.name)
    }

    createBtn.onclick = () => {
      if (!isConnected) return
      isCreator = true
      ws.send(JSON.stringify({ type: 'create' }))
      createBtn.disabled = true
      joinBtn.disabled = true
    }

    joinBtn.onclick = async () => {
      const code = manualCode.value.trim().toUpperCase()
      if (!code) return
      room = code
      isCreator = false
      encKey = await deriveKey(code)
      joinBtn.disabled = true
      createBtn.disabled = true
      if (isConnected) ws.send(JSON.stringify({ type: 'join', room }))
    }

    scanBtn.onclick = () => manualCode.focus()
    dropZone.onclick = () => fileInput.click()
    dropZone.ondragover = event => { event.preventDefault(); dropZone.classList.add('dragover') }
    dropZone.ondragleave = () => dropZone.classList.remove('dragover')
    dropZone.ondrop = event => {
      event.preventDefault()
      dropZone.classList.remove('dragover')
      if (event.dataTransfer.files[0]) sendFile(event.dataTransfer.files[0])
    }
    fileInput.onchange = () => {
      if (fileInput.files[0]) sendFile(fileInput.files[0])
      fileInput.value = ''
    }

    const initCode = new URLSearchParams(location.search).get('code')
    if (initCode) {
      room = initCode.trim().toUpperCase()
      manualCode.value = room
      joinBtn.disabled = false
    }

    connect()
  </script>
</body>
</html>`

interface SessionData {
  roomCode?: string
  peerId?: string
}

interface Room {
  creator: ServerWebSocket<SessionData>
  joiner: ServerWebSocket<SessionData> | null
  created: number
}

const rooms = new Map<string, Room>()

function genCode(len = 6) {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  let code = ""
  for (let i = 0; i < len; i += 1) code += chars[Math.floor(Math.random() * chars.length)]
  return code
}

function broadcast(room: Room, exclude: ServerWebSocket<SessionData>, msg: string) {
  if (room.creator !== exclude) room.creator.send(msg)
  if (room.joiner && room.joiner !== exclude) room.joiner.send(msg)
}

function leaveRoom(ws: ServerWebSocket<SessionData>, notifyPeer: boolean) {
  const roomCode = ws.data.roomCode
  if (!roomCode) return

  const room = rooms.get(roomCode)
  if (!room) {
    ws.data.roomCode = undefined
    ws.data.peerId = undefined
    return
  }

  if (room.creator === ws) {
    if (notifyPeer) room.joiner?.send(JSON.stringify({ type: "peer_leave" }))
    room.joiner?.close()
    rooms.delete(roomCode)
    console.log(`[Room ${roomCode}] Creator left`)
  } else {
    room.joiner = null
    if (notifyPeer) room.creator.send(JSON.stringify({ type: "peer_leave", peerId: ws.data.peerId }))
    console.log(`[Room ${roomCode}] Joiner left`)
  }

  ws.data.roomCode = undefined
  ws.data.peerId = undefined
}

Bun.serve({
  port: PORT,
  fetch(req, server) {
    const url = new URL(req.url)

    if (url.pathname === "/" || url.pathname === "/index.html") {
      return new Response(HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } })
    }

    const upgraded = server.upgrade(req, { data: {} satisfies SessionData })
    if (upgraded) return
    return new Response("WebSocket upgrade failed", { status: 500 })
  },

  websocket: {
    open() {},

    message(ws, data) {
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(data.toString())
      } catch {
        ws.send(JSON.stringify({ type: "error", message: "Invalid JSON" }))
        return
      }

      switch (msg.type) {
        case "create": {
          leaveRoom(ws, false)
          const roomCode = genCode()
          const peerId = genCode(4)
          ws.data.roomCode = roomCode
          ws.data.peerId = peerId
          rooms.set(roomCode, { creator: ws, joiner: null, created: Date.now() })
          ws.send(JSON.stringify({ type: "created", room: roomCode, peerId }))
          console.log(`[Room ${roomCode}] Created`)
          break
        }

        case "join": {
          const roomCode = String(msg.room ?? "").toUpperCase()
          const room = rooms.get(roomCode)
          if (!room) {
            ws.send(JSON.stringify({ type: "error", message: "Room not found" }))
            return
          }
          if (room.joiner && room.joiner !== ws) {
            ws.send(JSON.stringify({ type: "error", message: "Room full" }))
            return
          }

          leaveRoom(ws, false)
          const peerId = genCode(4)
          ws.data.roomCode = roomCode
          ws.data.peerId = peerId
          room.joiner = ws
          ws.send(JSON.stringify({ type: "joined", room: roomCode, peerId, peer: room.creator.data.peerId ?? null }))
          room.creator.send(JSON.stringify({ type: "peer_joined", peerId }))
          console.log(`[Room ${roomCode}] Joined`)
          break
        }

        case "relay": {
          const roomCode = ws.data.roomCode
          if (!roomCode) return
          const room = rooms.get(roomCode)
          if (!room) return
          broadcast(room, ws, JSON.stringify({ type: "relay", from: ws.data.peerId, data: msg.data }))
          break
        }

        case "done": {
          const roomCode = ws.data.roomCode
          if (!roomCode) return
          const room = rooms.get(roomCode)
          if (!room) return
          broadcast(room, ws, JSON.stringify({ type: "done", from: ws.data.peerId, hash: msg.hash ?? "" }))
          break
        }

        case "leave":
          leaveRoom(ws, true)
          break

        default:
          ws.send(JSON.stringify({ type: "error", message: "Unknown message type" }))
      }
    },

    close(ws) {
      leaveRoom(ws, true)
    },
  },
})

console.log(`[FAST P2P] Server running at http://0.0.0.0:${PORT}`)
console.log(`[FAST P2P] WebSocket ready at ws://0.0.0.0:${PORT}`)
