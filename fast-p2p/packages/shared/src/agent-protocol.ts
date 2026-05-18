export const AGENT_PROTOCOL = "fast-p2p-agent"
export const AGENT_PROTOCOL_VERSION = 1

export type AgentKind = "human" | "model" | "tool" | "runtime"

export type AgentCapabilityId =
  | "chat"
  | "tool-call"
  | "tool-result"
  | "memory-sync"
  | "model-context"
  | "file-transfer"
  | "budget-control"
  | "consent-request"
  | (string & {})

export type AgentPermission = "read" | "write" | "execute" | "delegate"

export interface AgentCapability {
  id: AgentCapabilityId
  version?: number
  permissions?: AgentPermission[]
  description?: string
}

export interface AgentDescriptor {
  nodeId: string
  kind: AgentKind
  displayName?: string
  publicKey?: string
  capabilities: AgentCapability[]
  metadata?: Record<string, string | number | boolean>
}

export interface AgentSessionOffer {
  sessionId: string
  createdAt: number
  requiredCapabilities?: AgentCapabilityId[]
  transport?: string
}

export type AgentHelloMessage = {
  type: "agent/hello"
  protocol: typeof AGENT_PROTOCOL
  version: typeof AGENT_PROTOCOL_VERSION
  from: AgentDescriptor
  offer: AgentSessionOffer
}

export type AgentAcceptMessage = {
  type: "agent/accept"
  protocol: typeof AGENT_PROTOCOL
  version: typeof AGENT_PROTOCOL_VERSION
  from: AgentDescriptor
  sessionId: string
  capabilities: AgentCapability[]
}

export type AgentRejectMessage = {
  type: "agent/reject"
  protocol: typeof AGENT_PROTOCOL
  version: typeof AGENT_PROTOCOL_VERSION
  sessionId: string
  reason: string
  missingCapabilities?: AgentCapabilityId[]
}

export type AgentControlPayload =
  | { kind: "chat"; text: string }
  | { kind: "tool-call"; callId: string; toolName: string; input: unknown }
  | { kind: "tool-result"; callId: string; ok: boolean; output?: unknown; error?: string }
  | { kind: "memory-sync"; scope: string; records: unknown[] }
  | { kind: "model-context"; label: string; content: string; tokenEstimate?: number }
  | { kind: "budget-control"; limit: number; unit: "tokens" | "seconds" | "requests" }
  | { kind: "consent-request"; requestId: string; action: string; detail?: string }
  | { kind: "opaque"; contentType: string; data: unknown }

export type AgentEnvelope = {
  type: "agent/envelope"
  protocol: typeof AGENT_PROTOCOL
  version: typeof AGENT_PROTOCOL_VERSION
  id: string
  sessionId: string
  sentAt: number
  from: string
  to?: string
  payload: AgentControlPayload
}

export type AgentProtocolMessage = AgentHelloMessage | AgentAcceptMessage | AgentRejectMessage | AgentEnvelope

export type AgentCapabilityNegotiation = {
  accepted: boolean
  common: AgentCapability[]
  missingRequired: AgentCapabilityId[]
}

function normalizeCapabilityId(id: AgentCapabilityId): AgentCapabilityId {
  return id.trim().toLowerCase() as AgentCapabilityId
}

function normalizeCapability(capability: AgentCapability): AgentCapability {
  return {
    ...capability,
    id: normalizeCapabilityId(capability.id),
    permissions: capability.permissions ? Array.from(new Set(capability.permissions)).sort() : undefined,
  }
}

function uniqueCapabilities(capabilities: AgentCapability[]): AgentCapability[] {
  const byId = new Map<AgentCapabilityId, AgentCapability>()

  for (const capability of capabilities) {
    const normalized = normalizeCapability(capability)
    const existing = byId.get(normalized.id)
    if (!existing || (normalized.version ?? 0) > (existing.version ?? 0)) {
      byId.set(normalized.id, normalized)
    }
  }

  return Array.from(byId.values()).sort((a, b) => a.id.localeCompare(b.id))
}

export function normalizeAgentDescriptor(descriptor: AgentDescriptor): AgentDescriptor {
  return {
    ...descriptor,
    nodeId: descriptor.nodeId.trim(),
    capabilities: uniqueCapabilities(descriptor.capabilities),
  }
}

export function negotiateAgentCapabilities(
  local: AgentCapability[],
  remote: AgentCapability[],
  required: AgentCapabilityId[] = [],
): AgentCapabilityNegotiation {
  const localById = new Map(uniqueCapabilities(local).map((capability) => [capability.id, capability]))
  const remoteById = new Map(uniqueCapabilities(remote).map((capability) => [capability.id, capability]))
  const common: AgentCapability[] = []

  for (const [id, localCapability] of localById) {
    const remoteCapability = remoteById.get(id)
    if (!remoteCapability) continue

    common.push({
      ...localCapability,
      version: Math.min(localCapability.version ?? 1, remoteCapability.version ?? 1),
      permissions:
        localCapability.permissions && remoteCapability.permissions
          ? localCapability.permissions.filter((permission) => remoteCapability.permissions?.includes(permission))
          : localCapability.permissions ?? remoteCapability.permissions,
    })
  }

  const commonIds = new Set(common.map((capability) => capability.id))
  const missingRequired = required
    .map((id) => normalizeCapabilityId(id))
    .filter((id) => !commonIds.has(id))

  return {
    accepted: missingRequired.length === 0,
    common: uniqueCapabilities(common),
    missingRequired,
  }
}

export function createAgentHello(descriptor: AgentDescriptor, offer: AgentSessionOffer): AgentHelloMessage {
  return {
    type: "agent/hello",
    protocol: AGENT_PROTOCOL,
    version: AGENT_PROTOCOL_VERSION,
    from: normalizeAgentDescriptor(descriptor),
    offer: {
      ...offer,
      requiredCapabilities: offer.requiredCapabilities?.map((id) => normalizeCapabilityId(id)),
    },
  }
}

export function createAgentAccept(
  descriptor: AgentDescriptor,
  sessionId: string,
  capabilities: AgentCapability[],
): AgentAcceptMessage {
  return {
    type: "agent/accept",
    protocol: AGENT_PROTOCOL,
    version: AGENT_PROTOCOL_VERSION,
    from: normalizeAgentDescriptor(descriptor),
    sessionId,
    capabilities: uniqueCapabilities(capabilities),
  }
}

export function createAgentReject(
  sessionId: string,
  reason: string,
  missingCapabilities: AgentCapabilityId[] = [],
): AgentRejectMessage {
  return {
    type: "agent/reject",
    protocol: AGENT_PROTOCOL,
    version: AGENT_PROTOCOL_VERSION,
    sessionId,
    reason,
    missingCapabilities: missingCapabilities.map((id) => normalizeCapabilityId(id)),
  }
}

export function createAgentEnvelope(args: Omit<AgentEnvelope, "type" | "protocol" | "version">): AgentEnvelope {
  return {
    type: "agent/envelope",
    protocol: AGENT_PROTOCOL,
    version: AGENT_PROTOCOL_VERSION,
    ...args,
  }
}

export function isAgentProtocolMessage(value: unknown): value is AgentProtocolMessage {
  if (!value || typeof value !== "object") return false
  const candidate = value as Partial<AgentProtocolMessage>
  return (
    candidate.protocol === AGENT_PROTOCOL &&
    candidate.version === AGENT_PROTOCOL_VERSION &&
    (candidate.type === "agent/hello" ||
      candidate.type === "agent/accept" ||
      candidate.type === "agent/reject" ||
      candidate.type === "agent/envelope")
  )
}
