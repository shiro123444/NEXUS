import crypto from "crypto"
import { EventEmitter } from "events"
import { encodeMessage, createMessageParser, type Message, type PeerInfo } from "./protocol"

export interface P2PSwarm {
  on(event: "peer-join", listener: (peerId: string, peer: PeerInfo) => void): this
  on(event: "peer-leave", listener: (peerId: string) => void): this
  on(event: "message", listener: (peerId: string, msg: Message) => void): this
  emit(event: "peer-join", peerId: string, peer: PeerInfo): boolean
  emit(event: "peer-leave", peerId: string): boolean
  emit(event: "message", peerId: string, msg: Message): boolean
  removeListener(event: string, listener: (...args: any[]) => void): this
}

export class P2PSwarm extends EventEmitter {
  private swarm: any = null
  private peers: Map<string, PeerInfo> = new Map()
  private name: string
  private topic: Buffer | null = null
  private code: string | null = null

  constructor(name?: string) {
    super()
    this.name = name ?? `peer-${crypto.randomBytes(2).toString("hex")}`
  }

  async init(): Promise<void> {
    if (typeof (globalThis as any).Bun !== "undefined") {
      throw new Error(
        "P2P swarm is not supported on Bun runtime yet (missing libuv uv_interface_addresses). Use Node.js to run this example.",
      )
    }

    const Hyperswarm = (await import("hyperswarm")).default
    this.swarm = new Hyperswarm()

    this.swarm.on("connection", (conn: any, info: any) => {
      const peerId = info.publicKey?.toString("hex")?.slice(0, 8) ?? crypto.randomBytes(4).toString("hex")

      const parser = createMessageParser((msg: Message) => {
        if (msg.type === "peer-info") {
          const peer: PeerInfo = { name: msg.name, connectedAt: Date.now(), conn }
          this.peers.set(peerId, peer)
          this.emit("peer-join", peerId, peer)
        } else {
          this.emit("message", peerId, msg)
        }
      })

      conn.on("data", parser)
      conn.on("close", () => {
        this.peers.delete(peerId)
        this.emit("peer-leave", peerId)
      })
      conn.on("error", () => {
        this.peers.delete(peerId)
        this.emit("peer-leave", peerId)
      })

      // Send our info
      conn.write(encodeMessage({ type: "peer-info", name: this.name }))
    })
  }

  generateCode(): string {
    this.code = crypto.randomBytes(3).toString("hex")
    return this.code
  }

  async joinTopic(code: string): Promise<void> {
    this.code = code
    this.topic = crypto.createHash("sha256").update(code).digest()
    const discovery = this.swarm.join(this.topic, { server: true, client: true })
    await discovery.flushed()
  }

  sendTo(peerId: string, msg: Message): void {
    const peer = this.peers.get(peerId)
    if (peer?.conn) {
      peer.conn.write(encodeMessage(msg))
    }
  }

  broadcast(msg: Message): void {
    const data = encodeMessage(msg)
    for (const peer of this.peers.values()) {
      if (peer.conn) {
        try {
          peer.conn.write(data)
        } catch {}
      }
    }
  }

  getPeers(): Map<string, PeerInfo> {
    return this.peers
  }

  getCode(): string | null {
    return this.code
  }

  getName(): string {
    return this.name
  }

  async destroy(): Promise<void> {
    if (this.swarm) {
      await this.swarm.destroy()
    }
  }
}
