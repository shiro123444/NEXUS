import type { EncryptedChunkPayload } from "./relay-protocol"
import { decryptRelayChunk, encryptRelayChunk, type RelayKey } from "./browser-crypto"
import {
  AGENT_PROTOCOL,
  AGENT_PROTOCOL_VERSION,
  isAgentProtocolMessage,
  type AgentProtocolMessage,
} from "./agent-protocol"

export type EncryptedAgentSignal = {
  kind: "agent/secure"
  protocol: typeof AGENT_PROTOCOL
  version: typeof AGENT_PROTOCOL_VERSION
  alg: "AES-GCM"
  contentType: "application/vnd.fast-p2p.agent+json"
  payload: EncryptedChunkPayload
}

const textEncoder = new TextEncoder()
const textDecoder = new TextDecoder()

export function isEncryptedAgentSignal(value: unknown): value is EncryptedAgentSignal {
  if (!value || typeof value !== "object") return false
  const candidate = value as Partial<EncryptedAgentSignal>
  return (
    candidate.kind === "agent/secure" &&
    candidate.protocol === AGENT_PROTOCOL &&
    candidate.version === AGENT_PROTOCOL_VERSION &&
    candidate.alg === "AES-GCM" &&
    candidate.contentType === "application/vnd.fast-p2p.agent+json" &&
    Boolean(candidate.payload)
  )
}

export async function encryptAgentSignal(message: AgentProtocolMessage, key: RelayKey): Promise<EncryptedAgentSignal> {
  const payload = await encryptRelayChunk(textEncoder.encode(JSON.stringify(message)), key)
  return {
    kind: "agent/secure",
    protocol: AGENT_PROTOCOL,
    version: AGENT_PROTOCOL_VERSION,
    alg: "AES-GCM",
    contentType: "application/vnd.fast-p2p.agent+json",
    payload,
  }
}

export async function decryptAgentSignal(signal: EncryptedAgentSignal, key: RelayKey): Promise<AgentProtocolMessage> {
  const decrypted = await decryptRelayChunk(signal.payload, key)
  const message = JSON.parse(textDecoder.decode(decrypted))

  if (!isAgentProtocolMessage(message)) {
    throw new Error("Invalid encrypted agent protocol message")
  }

  return message
}
