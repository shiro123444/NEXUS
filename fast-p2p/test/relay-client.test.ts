import { test } from "node:test"
import assert from "node:assert/strict"
import { RelayClient } from "../src/p2p/relay-client"
import { deriveKey, encryptChunk } from "../src/p2p/crypto"

test("relay client derives the creator key and decrypts incoming relay payloads", () => {
  const client = new RelayClient()
  const messages: Array<{ text: string; metaName?: string }> = []

  client.on("message", (data, _index, _total, meta) => {
    messages.push({ text: data.toString("utf8"), metaName: meta?.name })
  })

  ;(client as any).handleMessage({ type: "created", room: "ROOM01", peerId: "HOST" })
  const encrypted = encryptChunk(Buffer.from("hello"), deriveKey("ROOM01"))
  ;(client as any).handleMessage({
    type: "relay",
    data: {
      ...encrypted,
      index: 0,
      total: 1,
      _meta: { id: "tx1", name: "hello.txt", size: 5, total: 1, hash: "abc" },
    },
  })

  assert.deepEqual(messages, [{ text: "hello", metaName: "hello.txt" }])
})

test("relay client exposes the creator peer to a joiner", () => {
  const client = new RelayClient()
  const peers: string[] = []

  client.on("peer-join", (peerId) => {
    peers.push(peerId)
  })

  ;(client as any).handleMessage({ type: "joined", room: "ROOM01", peerId: "JOIN", peer: "HOST" })

  assert.deepEqual(peers, ["HOST"])
})
