import { test } from "node:test"
import assert from "node:assert/strict"
import { decryptRelayChunk, deriveRelayKey, encryptRelayChunk, sha256Hex } from "../packages/shared/src/browser-crypto"

async function withCryptoWithoutSubtle<T>(callback: () => Promise<T>) {
  const original = globalThis.crypto
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value: {
      getRandomValues: original.getRandomValues.bind(original),
      subtle: undefined,
    },
  })

  try {
    return await callback()
  } finally {
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: original,
    })
  }
}

test("browser crypto fallback can derive a key and round-trip AES-GCM payloads without subtle crypto", async () => {
  await withCryptoWithoutSubtle(async () => {
    const key = await deriveRelayKey("ROOM01")
    const payload = new TextEncoder().encode("hello lan")
    const encrypted = await encryptRelayChunk(payload, key)
    const decrypted = await decryptRelayChunk(encrypted, key)

    assert.equal(new TextDecoder().decode(decrypted), "hello lan")
  })
})

test("browser crypto fallback produces deterministic SHA-256 hex without subtle crypto", async () => {
  await withCryptoWithoutSubtle(async () => {
    const digest = await sha256Hex(new TextEncoder().encode("fast-p2p"))
    assert.equal(digest.length, 64)
  })
})
