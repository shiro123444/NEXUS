export type Message =
  | { type: "peer-info"; name: string }
  | { type: "offer"; id: string; filename: string; size: number; hash: string }
  | { type: "accept"; id: string }
  | { type: "reject"; id: string; reason: string }
  | { type: "chunk"; id: string; index: number; total: number; data: string }
  | { type: "done"; id: string; hash: string }
  | { type: "error"; id: string; message: string }

export const CHUNK_SIZE = 64 * 1024 // 64KB

export interface PeerInfo {
  name: string
  connectedAt: number
  conn: any
}

export interface TransferInfo {
  id: string
  filename: string
  size: number
  hash: string
  progress: number // 0-1
  speed: number // bytes/sec
  status: "pending" | "transferring" | "done" | "error"
  direction: "send" | "receive"
  error?: string
}

export function encodeMessage(msg: Message): Buffer {
  return Buffer.from(JSON.stringify(msg) + "\n")
}

export function createMessageParser(onMessage: (msg: Message) => void) {
  let buffer = ""
  return (chunk: Buffer) => {
    buffer += chunk.toString()
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""
    for (const line of lines) {
      if (line.trim()) {
        try {
          onMessage(JSON.parse(line))
        } catch {}
      }
    }
  }
}
