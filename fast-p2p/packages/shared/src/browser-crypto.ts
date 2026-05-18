import { gcm } from "@noble/ciphers/aes.js"
import { pbkdf2 } from "@noble/hashes/pbkdf2.js"
import { sha256 } from "@noble/hashes/sha2.js"
import type { EncryptedChunkPayload } from "./relay-protocol"

const PBKDF2_SALT = "fastp2p-salt"
const PBKDF2_ITERATIONS = 100000
const PBKDF2_HASH = "SHA-256"
const AES_GCM_TAG_BYTES = 16

export type RelayKey = CryptoKey | Uint8Array

function toUint8Array(data: ArrayBuffer | Uint8Array): Uint8Array {
  return data instanceof Uint8Array ? data : new Uint8Array(data)
}

function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  const sliced = data.byteOffset === 0 && data.byteLength === data.buffer.byteLength ? data : data.slice()
  return sliced.buffer as ArrayBuffer
}

function bytesToBase64(bytes: Uint8Array): string {
  let output = ""
  for (let index = 0; index < bytes.length; index += 0x8000) {
    output += String.fromCharCode(...bytes.subarray(index, index + 0x8000))
  }
  return btoa(output)
}

function base64ToBytes(value: string): Uint8Array {
  const raw = atob(value)
  const bytes = new Uint8Array(raw.length)
  for (let index = 0; index < raw.length; index++) {
    bytes[index] = raw.charCodeAt(index)
  }
  return bytes
}

function hasSubtleCrypto(): boolean {
  return typeof crypto !== "undefined" && typeof crypto.subtle !== "undefined"
}

function deriveRelayKeyFallback(code: string): Uint8Array {
  const encoder = new TextEncoder()
  return pbkdf2(sha256, encoder.encode(code), encoder.encode(PBKDF2_SALT), {
    c: PBKDF2_ITERATIONS,
    dkLen: 32,
  })
}

function getKeyBytes(key: RelayKey): Uint8Array {
  if (key instanceof Uint8Array) return key
  throw new Error("SubtleCrypto key required in this environment")
}

function getCryptoKey(key: RelayKey): CryptoKey {
  if (key instanceof Uint8Array) {
    throw new Error("Uint8Array key cannot be used with SubtleCrypto")
  }
  return key
}

export async function deriveRelayKey(code: string): Promise<RelayKey> {
  if (!hasSubtleCrypto()) {
    return deriveRelayKeyFallback(code)
  }

  const encoder = new TextEncoder()
  const material = await crypto.subtle.importKey("raw", encoder.encode(code), "PBKDF2", false, ["deriveBits"])
  const bits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt: encoder.encode(PBKDF2_SALT),
      iterations: PBKDF2_ITERATIONS,
      hash: PBKDF2_HASH,
    },
    material,
    256,
  )
  return crypto.subtle.importKey("raw", bits, { name: "AES-GCM" }, false, ["encrypt", "decrypt"])
}

export async function encryptRelayChunk(
  data: ArrayBuffer | Uint8Array,
  key: RelayKey,
): Promise<EncryptedChunkPayload> {
  const bytes = toUint8Array(data)
  const iv = crypto.getRandomValues(new Uint8Array(12))
  if (!hasSubtleCrypto()) {
    const encrypted = gcm(getKeyBytes(key), iv).encrypt(bytes)
    const authTag = encrypted.slice(encrypted.length - AES_GCM_TAG_BYTES)
    const cipher = encrypted.slice(0, encrypted.length - AES_GCM_TAG_BYTES)
    return {
      iv: bytesToBase64(iv),
      data: bytesToBase64(cipher),
      tag: bytesToBase64(authTag),
    }
  }

  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: toArrayBuffer(iv) },
    getCryptoKey(key),
    toArrayBuffer(bytes),
  )
  const encryptedBytes = new Uint8Array(encrypted)
  const authTag = encryptedBytes.slice(encryptedBytes.length - AES_GCM_TAG_BYTES)
  const cipher = encryptedBytes.slice(0, encryptedBytes.length - AES_GCM_TAG_BYTES)

  return {
    iv: bytesToBase64(iv),
    data: bytesToBase64(cipher),
    tag: bytesToBase64(authTag),
  }
}

export async function decryptRelayChunk(
  encrypted: EncryptedChunkPayload,
  key: RelayKey,
): Promise<Uint8Array> {
  const iv = base64ToBytes(encrypted.iv)
  const cipher = base64ToBytes(encrypted.data)
  const tag = base64ToBytes(encrypted.tag)
  const payload = new Uint8Array(cipher.length + tag.length)
  payload.set(cipher)
  payload.set(tag, cipher.length)
  if (!hasSubtleCrypto()) {
    return gcm(getKeyBytes(key), iv).decrypt(payload)
  }
  const decrypted = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: toArrayBuffer(iv) },
    getCryptoKey(key),
    toArrayBuffer(payload),
  )
  return new Uint8Array(decrypted)
}

export async function sha256Hex(data: ArrayBuffer | Uint8Array): Promise<string> {
  const bytes = toUint8Array(data)
  if (!hasSubtleCrypto()) {
    const digest = sha256(bytes)
    return Array.from(digest, (value) => Number(value).toString(16).padStart(2, "0")).join("")
  }
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", toArrayBuffer(bytes)))
  return Array.from(digest, (value) => Number(value).toString(16).padStart(2, "0")).join("")
}
