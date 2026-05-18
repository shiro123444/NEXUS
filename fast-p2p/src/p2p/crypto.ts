import * as crypto from "crypto"

const ALGORITHM = "aes-256-gcm"
const IV_LENGTH = 12
const AUTH_TAG_LENGTH = 16

export interface EncryptedChunk {
  iv: string
  data: string
  tag: string
}

export function deriveKey(code: string): Buffer {
  return crypto.pbkdf2Sync(code, "fastp2p-salt", 100000, 32, "sha256")
}

export function encryptChunk(data: Buffer, key: Buffer): EncryptedChunk {
  const iv = crypto.randomBytes(IV_LENGTH)
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv, { authTagLength: AUTH_TAG_LENGTH })
  const encrypted = Buffer.concat([cipher.update(data), cipher.final()])
  const tag = cipher.getAuthTag()
  return {
    iv: iv.toString("base64"),
    data: encrypted.toString("base64"),
    tag: tag.toString("base64"),
  }
}

export function decryptChunk(encrypted: EncryptedChunk, key: Buffer): Buffer {
  const iv = Buffer.from(encrypted.iv, "base64")
  const tag = Buffer.from(encrypted.tag, "base64")
  const data = Buffer.from(encrypted.data, "base64")
  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv, { authTagLength: AUTH_TAG_LENGTH })
  decipher.setAuthTag(tag)
  return Buffer.concat([decipher.update(data), decipher.final()])
}

export function encryptFile(
  filePath: string,
  roomCode: string,
  onChunk: (chunk: EncryptedChunk, index: number, total: number) => void,
): { filename: string; size: number; hash: string; totalChunks: number } {
  const fs = require("fs")
  const path = require("path")

  const stat = fs.statSync(filePath)
  const filename = path.basename(filePath)
  const key = deriveKey(roomCode)
  const CHUNK_SIZE = 32 * 1024

  const hash = crypto.createHash("sha256")
  const totalChunks = Math.ceil(stat.size / CHUNK_SIZE)
  let index = 0

  const stream = fs.createReadStream(filePath, { highWaterMark: CHUNK_SIZE })

  return new Promise((resolve, reject) => {
    stream.on("data", (chunk: Buffer) => {
      hash.update(chunk)
      const encrypted = encryptChunk(chunk, key)
      onChunk(encrypted, index, totalChunks)
      index++
    })

    stream.on("end", () => {
      resolve({
        filename,
        size: stat.size,
        hash: hash.digest("hex"),
        totalChunks,
      })
    })

    stream.on("error", reject)
  }) as any
}
