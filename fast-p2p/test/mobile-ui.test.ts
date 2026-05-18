import { test } from "node:test"
import assert from "node:assert/strict"
import {
  getInitialCommandInput,
  getMobilePrimaryActions,
  type MobileActionContext,
} from "../apps/web/src/lib/mobile-ui"

test("getInitialCommandInput stays empty even when room code comes from URL", () => {
  assert.equal(getInitialCommandInput("R6VPH7"), "")
  assert.equal(getInitialCommandInput(""), "")
})

test("getMobilePrimaryActions prioritizes room creation before session actions exist", () => {
  const context: MobileActionContext = {
    roomCode: "",
    hasRoomLink: false,
    peerConnected: false,
  }

  assert.deepEqual(
    getMobilePrimaryActions(context).map((item) => item.id),
    ["create-room", "join-room"],
  )
})

test("getMobilePrimaryActions returns task-first actions inside a room", () => {
  const context: MobileActionContext = {
    roomCode: "ROOM01",
    hasRoomLink: true,
    peerConnected: true,
  }

  assert.deepEqual(
    getMobilePrimaryActions(context).map((item) => item.id),
    ["pick-file", "copy-link", "leave-room"],
  )
})
