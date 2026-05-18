import { test } from "node:test"
import assert from "node:assert/strict"
import { deriveRelayUrl } from "../apps/web/src/lib/relay-url"

test("deriveRelayUrl uses explicit relay URL when provided", () => {
  assert.equal(
    deriveRelayUrl({
      explicit: "wss://relay.example.com/ws",
      search: "",
      protocol: "https:",
      hostname: "example.com",
      host: "example.com",
      port: "",
    }),
    "wss://relay.example.com/ws",
  )
})

test("deriveRelayUrl uses query param relay override when present", () => {
  assert.equal(
    deriveRelayUrl({
      explicit: "",
      search: "?relay=ws://192.168.31.232:3000/ws",
      protocol: "http:",
      hostname: "192.168.31.232",
      host: "192.168.31.232:4173",
      port: "4173",
    }),
    "ws://192.168.31.232:3000/ws",
  )
})

test("deriveRelayUrl rewrites dev frontend ports to relay port on LAN hosts", () => {
  assert.equal(
    deriveRelayUrl({
      explicit: "",
      search: "",
      protocol: "http:",
      hostname: "192.168.31.232",
      host: "192.168.31.232:4173",
      port: "4173",
    }),
    "ws://192.168.31.232:3000/ws",
  )
})

test("deriveRelayUrl keeps production host when using standard web ports", () => {
  assert.equal(
    deriveRelayUrl({
      explicit: "",
      search: "",
      protocol: "https:",
      hostname: "fast-p2p.example.com",
      host: "fast-p2p.example.com",
      port: "",
    }),
    "wss://fast-p2p.example.com/ws",
  )
})
