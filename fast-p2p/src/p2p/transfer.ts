import fs from "fs"
import path from "path"
import crypto from "crypto"
import { CHUNK_SIZE, encodeMessage, type Message, type TransferInfo } from "./protocol"
import type { P2PSwarm } from "./swarm"

export async function computeFileHash(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256")
    const stream = fs.createReadStream(filePath)
    stream.on("data", (chunk) => hash.update(chunk))
    stream.on("end", () => resolve(hash.digest("hex")))
    stream.on("error", reject)
  })
}

export async function sendFile(
  swarm: P2PSwarm,
  peerId: string,
  filePath: string,
  onProgress: (transfer: TransferInfo) => void,
): Promise<void> {
  const stat = fs.statSync(filePath)
  const filename = path.basename(filePath)
  const hash = await computeFileHash(filePath)
  const id = crypto.randomBytes(4).toString("hex")
  const totalChunks = Math.ceil(stat.size / CHUNK_SIZE)

  const transfer: TransferInfo = {
    id,
    filename,
    size: stat.size,
    hash,
    progress: 0,
    speed: 0,
    status: "pending",
    direction: "send",
  }

  // Send offer
  swarm.sendTo(peerId, { type: "offer", id, filename, size: stat.size, hash })
  onProgress(transfer)

  // Wait for accept/reject via a promise
  return new Promise((resolve, reject) => {
    const handler = (_pid: string, msg: Message) => {
      if (msg.type === "accept" && msg.id === id) {
        swarm.removeListener("message", handler)
        doSend()
      } else if (msg.type === "reject" && msg.id === id) {
        swarm.removeListener("message", handler)
        transfer.status = "error"
        transfer.error = (msg as any).reason ?? "Rejected"
        onProgress(transfer)
        reject(new Error("Transfer rejected"))
      }
    }
    swarm.on("message", handler)

    async function doSend() {
      transfer.status = "transferring"
      const startTime = Date.now()
      let sentBytes = 0
      let chunkIndex = 0

      const stream = fs.createReadStream(filePath, { highWaterMark: CHUNK_SIZE })

      for await (const chunk of stream) {
        const data = (chunk as Buffer).toString("base64")
        swarm.sendTo(peerId, {
          type: "chunk",
          id,
          index: chunkIndex,
          total: totalChunks,
          data,
        })
        sentBytes += (chunk as Buffer).length
        chunkIndex++

        const elapsed = (Date.now() - startTime) / 1000
        transfer.progress = sentBytes / stat.size
        transfer.speed = elapsed > 0 ? sentBytes / elapsed : 0
        onProgress(transfer)
      }

      swarm.sendTo(peerId, { type: "done", id, hash })
      transfer.status = "done"
      transfer.progress = 1
      onProgress(transfer)
      resolve()
    }
  })
}

export function handleIncomingTransfer(
  swarm: P2PSwarm,
  peerId: string,
  offer: Extract<Message, { type: "offer" }>,
  savePath: string,
  onProgress: (transfer: TransferInfo) => void,
): TransferInfo {
  const transfer: TransferInfo = {
    id: offer.id,
    filename: offer.filename,
    size: offer.size,
    hash: offer.hash,
    progress: 0,
    speed: 0,
    status: "transferring",
    direction: "receive",
  }

  if (!fs.existsSync(savePath)) {
    fs.mkdirSync(savePath, { recursive: true })
  }

  const filePath = path.join(savePath, offer.filename)
  const writeStream = fs.createWriteStream(filePath)
  let receivedBytes = 0
  const startTime = Date.now()

  // Accept the transfer
  swarm.sendTo(peerId, { type: "accept", id: offer.id })
  onProgress(transfer)

  const handler = (_pid: string, msg: Message) => {
    if (msg.type === "chunk" && msg.id === offer.id) {
      const buf = Buffer.from(msg.data, "base64")
      writeStream.write(buf)
      receivedBytes += buf.length

      const elapsed = (Date.now() - startTime) / 1000
      transfer.progress = receivedBytes / offer.size
      transfer.speed = elapsed > 0 ? receivedBytes / elapsed : 0
      onProgress(transfer)
    } else if (msg.type === "done" && msg.id === offer.id) {
      writeStream.end(async () => {
        swarm.removeListener("message", handler)
        // Verify hash
        const actualHash = await computeFileHash(filePath)
        if (actualHash === msg.hash) {
          transfer.status = "done"
          transfer.progress = 1
        } else {
          transfer.status = "error"
          transfer.error = "Hash mismatch"
        }
        onProgress(transfer)
      })
    } else if (msg.type === "error" && msg.id === offer.id) {
      swarm.removeListener("message", handler)
      writeStream.end()
      transfer.status = "error"
      transfer.error = msg.message
      onProgress(transfer)
    }
  }

  writeStream.on("error", (err) => {
    swarm.removeListener("message", handler)
    transfer.status = "error"
    transfer.error = err.message
    onProgress(transfer)
  })

  swarm.on("message", handler)
  return transfer
}
