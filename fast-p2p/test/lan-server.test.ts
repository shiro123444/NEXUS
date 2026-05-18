import { test } from "node:test"
import assert from "node:assert/strict"
import { setTimeout as delay } from "node:timers/promises"
import { WebSocket } from "ws"
import { createLanServer } from "../src/p2p/lan-server"

test("createLanServer serves html, relays websocket messages, and reports peer lifecycle", async (t) => {
  const events: string[] = []
  const messages: Array<{ type: string; filename?: string }> = []

  const server = await createLanServer({
    port: 0,
    roomCode: "ROOM42",
    html: "<html><body>FAST P2P LAN</body></html>",
    onPeerConnected() {
      events.push("connected")
    },
    onPeerDisconnected() {
      events.push("disconnected")
    },
    onMessage(msg) {
      messages.push(msg)
    },
  })

  t.after(async () => {
    await server.stop()
  })

  const health = await fetch(`${server.url}/health`)
  assert.equal(await health.text(), "OK")

  const page = await fetch(server.url)
  assert.match(await page.text(), /FAST P2P LAN/)

  const peer = new WebSocket(`${server.wsBaseUrl}/ROOM42`)
  await new Promise<void>((resolve, reject) => {
    peer.once("open", () => resolve())
    peer.once("error", reject)
  })

  peer.send(JSON.stringify({ type: "file_start", filename: "hello.txt", size: 5, total: 1 }))
  await delay(100)
  assert.deepEqual(events, ["connected"])
  assert.equal(messages[0]?.type, "file_start")
  assert.equal(messages[0]?.filename, "hello.txt")

  peer.close()
  await delay(100)
  assert.deepEqual(events, ["connected", "disconnected"])
})
