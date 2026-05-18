import { test } from "node:test"
import assert from "node:assert/strict"
import {
  createAgentAccept,
  createAgentEnvelope,
  createAgentHello,
  createAgentReject,
  isAgentProtocolMessage,
  negotiateAgentCapabilities,
  normalizeAgentDescriptor,
  type AgentDescriptor,
} from "../packages/shared/src/agent-protocol"
import {
  decryptAgentSignal,
  encryptAgentSignal,
  isEncryptedAgentSignal,
} from "../packages/shared/src/agent-security"
import { deriveRelayKey } from "../packages/shared/src/browser-crypto"

const localAgent: AgentDescriptor = {
  nodeId: "local-node",
  kind: "model",
  displayName: "Local agent",
  capabilities: [
    { id: "CHAT", version: 1 },
    { id: "tool-call", version: 2, permissions: ["execute", "read", "execute"] },
    { id: "memory-sync", version: 1, permissions: ["read", "write"] },
  ],
}

const remoteAgent: AgentDescriptor = {
  nodeId: "remote-node",
  kind: "runtime",
  capabilities: [
    { id: "chat", version: 1 },
    { id: "tool-call", version: 1, permissions: ["execute"] },
    { id: "file-transfer", version: 1 },
  ],
}

test("normalizeAgentDescriptor deduplicates and normalizes capabilities", () => {
  assert.deepEqual(normalizeAgentDescriptor(localAgent).capabilities, [
    { id: "chat", version: 1, permissions: undefined },
    { id: "memory-sync", version: 1, permissions: ["read", "write"] },
    { id: "tool-call", version: 2, permissions: ["execute", "read"] },
  ])
})

test("negotiateAgentCapabilities accepts when required capabilities overlap", () => {
  const result = negotiateAgentCapabilities(localAgent.capabilities, remoteAgent.capabilities, ["chat", "tool-call"])

  assert.equal(result.accepted, true)
  assert.deepEqual(
    result.common.map((capability) => [capability.id, capability.version, capability.permissions]),
    [
      ["chat", 1, undefined],
      ["tool-call", 1, ["execute"]],
    ],
  )
})

test("negotiateAgentCapabilities reports missing required capabilities", () => {
  const result = negotiateAgentCapabilities(localAgent.capabilities, remoteAgent.capabilities, ["memory-sync"])

  assert.equal(result.accepted, false)
  assert.deepEqual(result.missingRequired, ["memory-sync"])
})

test("agent handshake helpers emit versioned protocol messages", () => {
  const hello = createAgentHello(localAgent, {
    sessionId: "session-1",
    createdAt: 123,
    requiredCapabilities: ["CHAT", "tool-call"],
    transport: "relay",
  })
  const negotiation = negotiateAgentCapabilities(remoteAgent.capabilities, hello.from.capabilities, hello.offer.requiredCapabilities)
  const accept = createAgentAccept(remoteAgent, hello.offer.sessionId, negotiation.common)
  const reject = createAgentReject(hello.offer.sessionId, "missing capability", ["memory-sync"])

  assert.equal(isAgentProtocolMessage(hello), true)
  assert.equal(isAgentProtocolMessage(accept), true)
  assert.equal(isAgentProtocolMessage(reject), true)
  assert.deepEqual(hello.offer.requiredCapabilities, ["chat", "tool-call"])
})

test("createAgentEnvelope wraps AI control payloads for any transport", () => {
  const envelope = createAgentEnvelope({
    id: "msg-1",
    sessionId: "session-1",
    sentAt: 456,
    from: "local-node",
    to: "remote-node",
    payload: {
      kind: "tool-call",
      callId: "call-1",
      toolName: "searchMemory",
      input: { query: "transport" },
    },
  })

  assert.equal(isAgentProtocolMessage(envelope), true)
  assert.equal(envelope.payload.kind, "tool-call")
})

test("encrypted agent signals hide and recover protocol messages with the relay session key", async () => {
  const key = await deriveRelayKey("ROOM01 SECRET77")
  const hello = createAgentHello(localAgent, {
    sessionId: "session-1",
    createdAt: 123,
    requiredCapabilities: ["chat"],
  })

  const encrypted = await encryptAgentSignal(hello, key)
  assert.equal(isEncryptedAgentSignal(encrypted), true)
  assert.equal(JSON.stringify(encrypted).includes("Local agent"), false)

  const decrypted = await decryptAgentSignal(encrypted, key)
  assert.deepEqual(decrypted, JSON.parse(JSON.stringify(hello)))
})
