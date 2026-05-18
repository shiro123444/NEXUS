import { test } from "node:test"
import assert from "node:assert/strict"
import { createRelayTransport, type RelayTransportSocket } from "../apps/web/src/lib/relay-transport"

class FakeSocket implements RelayTransportSocket {
  readyState = 0
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  sent: string[] = []

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = 3
    this.onclose?.()
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }

  receive(data: unknown) {
    this.onmessage?.({ data })
  }

  drop() {
    this.readyState = 3
    this.onclose?.()
  }
}

test("relay transport emits state transitions and parsed messages", () => {
  const sockets: FakeSocket[] = []
  const states: string[] = []
  const messages: Array<{ type: string }> = []

  const transport = createRelayTransport({
    url: "ws://relay.test/ws",
    socketFactory: () => {
      const socket = new FakeSocket()
      sockets.push(socket)
      return socket
    },
  })

  transport.on("state", (state) => states.push(state))
  transport.on("message", (message) => messages.push(message))

  transport.connect()
  assert.deepEqual(states, ["connecting"])

  sockets[0]!.open()
  assert.equal(transport.state, "online")
  assert.deepEqual(states, ["connecting", "online"])

  sockets[0]!.receive(JSON.stringify({ type: "created", room: "ROOM01", peerId: "PEER" }))
  assert.equal(messages[0]?.type, "created")

  assert.equal(transport.send({ type: "leave" }), true)
  assert.deepEqual(JSON.parse(sockets[0]!.sent[0]!), { type: "leave" })
})

test("relay transport reconnects after a remote close", async () => {
  const sockets: FakeSocket[] = []
  const states: string[] = []

  const transport = createRelayTransport({
    url: "ws://relay.test/ws",
    reconnectDelay: 0,
    socketFactory: () => {
      const socket = new FakeSocket()
      sockets.push(socket)
      return socket
    },
  })

  transport.on("state", (state) => states.push(state))

  transport.connect()
  sockets[0]!.open()
  sockets[0]!.drop()

  await new Promise((resolve) => setTimeout(resolve, 5))

  assert.equal(states.includes("offline"), true)
  assert.equal(sockets.length, 2)

  transport.disconnect()
})
