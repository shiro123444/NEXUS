import { deriveKey, decryptChunk, type EncryptedChunk } from "./crypto"

export interface RelayFileMeta {
  id: string
  name: string
  size: number
  total: number
  hash?: string
}

export interface RelayClientEvents {
  "peer-join": (peerId: string) => void
  "peer-leave": () => void
  message: (data: Buffer, index: number, total: number, meta?: RelayFileMeta | null) => void
  done: (hash: string) => void
  error: (err: Error) => void
}

export class RelayClient {
  private ws: WebSocket | null = null
  private room: string | null = null
  private peerId: string | null = null
  private peer: string | null = null
  private key: Buffer | null = null
  private pendingCreateKey: string | null = null
  private listeners: Map<string, Set<Function>> = new Map()
  private connected = false

  get isConnected() {
    return this.connected
  }

  get roomCode() {
    return this.room
  }

  on<T extends keyof RelayClientEvents>(event: T, cb: RelayClientEvents[T]): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(cb)
  }

  off<T extends keyof RelayClientEvents>(event: T, cb: RelayClientEvents[T]): void {
    this.listeners.get(event)?.delete(cb)
  }

  private emit<T extends keyof RelayClientEvents>(event: T, ...args: Parameters<RelayClientEvents[T]>) {
    this.listeners.get(event)?.forEach((cb) => (cb as any)(...args))
  }

  async connect(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        this.connected = true
        resolve()
      }

      this.ws.onerror = (err) => {
        this.emit("error", new Error(`WebSocket error`))
        reject(err)
      }

      this.ws.onclose = () => {
        this.connected = false
        this.emit("peer-leave")
      }

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          this.handleMessage(msg)
        } catch (err) {
          // ignore parse errors
        }
      }
    })
  }

  private handleMessage(msg: any) {
    switch (msg.type) {
      case "created":
        this.room = msg.room
        this.peerId = msg.peerId
        this.peer = null
        this.key = deriveKey(this.pendingCreateKey ?? msg.room)
        this.pendingCreateKey = null
        break

      case "joined":
        this.room = msg.room
        this.peerId = msg.peerId
        this.peer = msg.peer ?? null
        if (!this.key) this.key = deriveKey(msg.room)
        if (this.peer) this.emit("peer-join", this.peer)
        break

      case "peer_joined":
        this.peer = msg.peerId
        this.emit("peer-join", msg.peerId)
        break

      case "peer_leave":
        this.peer = null
        this.emit("peer-leave")
        break

      case "relay":
        if (!this.key) return
        try {
          const chunk: EncryptedChunk = {
            iv: msg.data.iv,
            data: msg.data.data,
            tag: msg.data.tag,
          }
          const decrypted = decryptChunk(chunk, this.key)
          const meta = (msg.data._meta ?? msg.data.meta ?? null) as RelayFileMeta | null
          this.emit("message", decrypted, msg.data.index, msg.data.total, meta)
        } catch (err) {
          this.emit("error", new Error("Decryption failed"))
        }
        break

      case "done":
        this.emit("done", msg.hash)
        break

      case "error":
        this.emit("error", new Error(msg.message))
        break
    }
  }

  createRoom(keyCode?: string): void {
    this.pendingCreateKey = keyCode ?? null
    this.ws?.send(JSON.stringify({ type: "create" }))
  }

  joinRoom(roomCode: string, keyCode: string): void {
    this.room = roomCode
    this.key = deriveKey(keyCode)
    this.ws?.send(JSON.stringify({ type: "join", room: roomCode }))
  }

  sendChunk(chunk: EncryptedChunk, index: number, total: number, meta?: RelayFileMeta | null): void {
    this.ws?.send(
      JSON.stringify({
        type: "relay",
        data: { iv: chunk.iv, data: chunk.data, tag: chunk.tag, index, total, _meta: meta ?? null },
      }),
    )
  }

  sendDone(hash: string): void {
    this.ws?.send(JSON.stringify({ type: "done", hash }))
  }

  disconnect(): void {
    this.ws?.send(JSON.stringify({ type: "leave" }))
    this.ws?.close()
    this.ws = null
    this.room = null
    this.peer = null
    this.key = null
    this.connected = false
  }
}
