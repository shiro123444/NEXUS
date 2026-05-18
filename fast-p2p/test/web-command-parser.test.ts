import { test } from "node:test"
import assert from "node:assert/strict"
import {
  getCommandSuggestions,
  parseCommandInput,
  type CommandContext,
} from "../apps/web/src/lib/command-parser"

const baseContext: CommandContext = {
  roomCode: "",
  peerConnected: false,
  hasRoomLink: false,
}

test("parseCommandInput resolves natural create room intent", () => {
  assert.deepEqual(parseCommandInput("创建房间", baseContext), {
    kind: "create-room",
  })
})

test("parseCommandInput resolves slash create command", () => {
  assert.deepEqual(parseCommandInput("/create", baseContext), {
    kind: "create-room",
  })
})

test("parseCommandInput resolves join room with normalized code", () => {
  assert.deepEqual(parseCommandInput("加入 room01", baseContext), {
    kind: "join-room",
    roomCode: "ROOM01",
    sessionSecret: null,
  })
})

test("parseCommandInput resolves join room with detached session secret", () => {
  assert.deepEqual(parseCommandInput("加入 room01 k3y9z8", baseContext), {
    kind: "join-room",
    roomCode: "ROOM01",
    sessionSecret: "K3Y9Z8",
  })
})

test("parseCommandInput resolves invite URLs that carry the session secret in the hash", () => {
  assert.deepEqual(parseCommandInput("加入 https://fast-p2p.test/?room=room01#key=secret77", baseContext), {
    kind: "join-room",
    roomCode: "ROOM01",
    sessionSecret: "SECRET77",
  })
})

test("parseCommandInput resolves copy link only when available", () => {
  assert.deepEqual(parseCommandInput("复制链接", { ...baseContext, hasRoomLink: true }), {
    kind: "copy-link",
  })

  assert.deepEqual(parseCommandInput("复制链接", baseContext), {
    kind: "invalid",
    reason: "当前还没有可复制的链接",
  })
})

test("parseCommandInput resolves send file intent only when peer is connected", () => {
  assert.deepEqual(parseCommandInput("发送文件", { ...baseContext, roomCode: "ROOM01", peerConnected: true }), {
    kind: "pick-file",
  })

  assert.deepEqual(parseCommandInput("发送文件", { ...baseContext, roomCode: "ROOM01", peerConnected: false }), {
    kind: "invalid",
    reason: "请先等待对端接入房间",
  })
})

test("getCommandSuggestions prioritizes room creation before session-only actions", () => {
  const suggestions = getCommandSuggestions("", baseContext)
  assert.equal(suggestions[0]?.label, "创建房间")
  assert.equal(suggestions[0]?.behavior, "execute")
  assert.equal(suggestions[1]?.behavior, "prefill")
  assert.equal(suggestions.some((item) => item.label === "发送文件"), false)
})

test("getCommandSuggestions filters by natural input prefix", () => {
  const suggestions = getCommandSuggestions("复", { ...baseContext, roomCode: "ROOM01", hasRoomLink: true })
  assert.deepEqual(
    suggestions.map((item) => item.label),
    ["复制链接", "复制房间码"],
  )
})
