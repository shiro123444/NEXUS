import { test } from "node:test"
import assert from "node:assert/strict"
import {
  buildRelayInviteLink,
  buildRelayJoinToken,
  createRelaySessionSecret,
  parseRelayInvite,
  parseRelayJoinToken,
} from "../packages/shared/src/relay-session"

test("createRelaySessionSecret produces uppercase invite-safe secrets", () => {
  const secret = createRelaySessionSecret(20)
  assert.match(secret, /^[A-Z2-9]{20}$/)
})

test("buildRelayInviteLink stores the room in search and the secret in the hash", () => {
  const link = buildRelayInviteLink("https://fast-p2p.test/app", "room01", "secret77")
  assert.equal(link, "https://fast-p2p.test/app?room=ROOM01#key=SECRET77")
})

test("parseRelayInvite reads room and key from browser location parts", () => {
  assert.deepEqual(
    parseRelayInvite({
      search: "?room=room01",
      hash: "#key=secret77",
    }),
    {
      roomCode: "ROOM01",
      sessionSecret: "SECRET77",
    },
  )
})

test("buildRelayJoinToken keeps manual sharing compact", () => {
  assert.equal(buildRelayJoinToken("room01", "secret77"), "ROOM01 SECRET77")
})

test("parseRelayJoinToken accepts compact join tokens and legacy room-only tokens", () => {
  assert.deepEqual(parseRelayJoinToken("room01 secret77"), {
    roomCode: "ROOM01",
    sessionSecret: "SECRET77",
  })

  assert.deepEqual(parseRelayJoinToken("room01"), {
    roomCode: "ROOM01",
    sessionSecret: null,
  })
})
