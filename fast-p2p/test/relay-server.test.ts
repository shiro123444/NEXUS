import { test } from "node:test"
import assert from "node:assert/strict"
import { createRelayRooms, type RelaySocket } from "../src/p2p/relay-rooms"

class MockSocket implements RelaySocket {
  data: { roomCode?: string; peerId?: string } = {}
  messages: Array<Record<string, unknown>> = []
  closed = false

  send(message: string): void {
    this.messages.push(JSON.parse(message))
  }

  close(): void {
    this.closed = true
  }
}

test("relay rooms emit peer_leave when a joiner disconnects", async () => {
  let codes = ["ROOM01", "PEER", "JOIN"]
  const relayRooms = createRelayRooms(() => {
    const next = codes.shift()
    if (!next) throw new Error("Ran out of test codes")
    return next
  })

  const creator = new MockSocket()
  const joiner = new MockSocket()

  relayRooms.handleMessage(creator, { type: "create" })
  assert.equal(creator.messages[0]?.type, "created")
  assert.equal(creator.data.roomCode, "ROOM01")

  relayRooms.handleMessage(joiner, { type: "join", room: "ROOM01" })
  assert.equal(joiner.messages[0]?.type, "joined")
  assert.equal(joiner.messages[0]?.peer, "PEER")
  assert.equal(creator.messages[1]?.type, "peer_joined")

  relayRooms.handleClose(joiner)
  assert.equal(creator.messages[2]?.type, "peer_leave")
})

test("relay rooms forward transfer completion hashes", () => {
  let codes = ["ROOM02", "HOST", "JOIN"]
  const relayRooms = createRelayRooms(() => {
    const next = codes.shift()
    if (!next) throw new Error("Ran out of test codes")
    return next
  })

  const creator = new MockSocket()
  const joiner = new MockSocket()

  relayRooms.handleMessage(creator, { type: "create" })
  relayRooms.handleMessage(joiner, { type: "join", room: "ROOM02" })
  relayRooms.handleMessage(creator, { type: "done", hash: "abc123" })

  assert.equal(joiner.messages[1]?.type, "done")
  assert.equal(joiner.messages[1]?.hash, "abc123")
})

test("relay rooms allow the creator to reconnect within the grace window", () => {
  let codes = ["ROOM03", "HOST", "JOIN"]
  const relayRooms = createRelayRooms(() => {
    const next = codes.shift()
    if (!next) throw new Error("Ran out of test codes")
    return next
  })

  const creator = new MockSocket()
  const joiner = new MockSocket()

  relayRooms.handleMessage(creator, { type: "create" })
  relayRooms.handleMessage(joiner, { type: "join", room: "ROOM03" })

  relayRooms.handleClose(creator)
  assert.equal(joiner.messages.at(-1)?.type, "peer_leave")

  const reconnectingCreator = new MockSocket()
  relayRooms.handleMessage(reconnectingCreator, { type: "reconnect", room: "ROOM03", peerId: "HOST", role: "creator" })

  assert.equal(reconnectingCreator.messages[0]?.type, "reconnected")
  assert.equal(reconnectingCreator.messages[0]?.peer, "JOIN")
  assert.equal(joiner.messages.at(-1)?.type, "peer_joined")
})
