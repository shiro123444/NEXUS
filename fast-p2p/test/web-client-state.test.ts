import { test } from "node:test"
import assert from "node:assert/strict"
import {
  buildRoomLink,
  createIncomingTransfer,
  createOutgoingTransfer,
  patchTransferList,
  removeTransfer,
  resolveStageLabel,
} from "../apps/web/src/lib/client-state"

test("buildRoomLink returns an empty string when no room code is present", () => {
  assert.equal(buildRoomLink("https://fast-p2p.dev", ""), "")
})

test("buildRoomLink appends the normalized room code to the current origin", () => {
  assert.equal(buildRoomLink("https://fast-p2p.dev", "ROOM01"), "https://fast-p2p.dev/?room=ROOM01")
})

test("createOutgoingTransfer seeds a pending send transfer", () => {
  assert.deepEqual(createOutgoingTransfer("tx-1", "demo.zip", 2048), {
    id: "tx-1",
    name: "demo.zip",
    size: 2048,
    direction: "send",
    status: "pending",
    progress: 0,
    detail: "等待发送",
  })
})

test("patchTransferList updates an existing transfer in place", () => {
  const current = [createOutgoingTransfer("tx-1", "demo.zip", 2048)]
  const next = patchTransferList(current, "tx-1", {
    status: "transferring",
    progress: 0.5,
    detail: "50%",
  })

  assert.equal(next.length, 1)
  assert.deepEqual(next[0], {
    id: "tx-1",
    name: "demo.zip",
    size: 2048,
    direction: "send",
    status: "transferring",
    progress: 0.5,
    detail: "50%",
  })
})

test("patchTransferList can seed a missing incoming transfer", () => {
  const next = patchTransferList(
    [],
    "rx-1",
    {
      status: "transferring",
      progress: 0.25,
      detail: "25%",
    },
    createIncomingTransfer("rx-1", "photo.png", 4096),
  )

  assert.deepEqual(next, [
    {
      id: "rx-1",
      name: "photo.png",
      size: 4096,
      direction: "receive",
      status: "transferring",
      progress: 0.25,
      detail: "25%",
    },
  ])
})

test("removeTransfer drops only the matching transfer", () => {
  const current = [
    createOutgoingTransfer("tx-1", "demo.zip", 2048),
    createIncomingTransfer("rx-1", "photo.png", 4096),
  ]

  const next = removeTransfer(current, "tx-1")

  assert.equal(next.length, 1)
  assert.equal(next[0]?.id, "rx-1")
})

test("resolveStageLabel prefers peer readiness over room waiting state", () => {
  assert.equal(resolveStageLabel("", false), "创建房间")
  assert.equal(resolveStageLabel("ROOM01", false), "等待对端")
  assert.equal(resolveStageLabel("ROOM01", true), "对端已就绪")
})
