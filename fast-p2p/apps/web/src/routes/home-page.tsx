import { AnimatePresence, motion } from "motion/react"
import { useEffect, useMemo, useRef, useState } from "react"
import QRCode from "qrcode"
import {
  RELAY_CHUNK_SIZE,
  buildRelayInviteLink,
  buildRelayJoinToken,
  createAgentAccept,
  createAgentHello,
  createAgentReject,
  createRelaySessionSecret,
  decryptAgentSignal,
  decryptRelayChunk,
  deriveRelayKey,
  encryptAgentSignal,
  encryptRelayChunk,
  isAgentProtocolMessage,
  isEncryptedAgentSignal,
  negotiateAgentCapabilities,
  normalizeRoomCode,
  parseRelayInvite,
  sha256Hex,
  type AgentCapability,
  type AgentDescriptor,
  type AgentProtocolMessage,
  type RelayKey,
  type RelayChunkPayload,
  type RelayClientMessage,
  type RelayFileMeta,
  type RelayServerMessage,
} from "@fast-p2p/shared"
import { ToastContainer, type ToastMessage } from "../components/Toast"
import { TransferList } from "../components/TransferList"
import type { TransferState } from "../components/TransferItem"
import {
  getCommandSuggestions,
  parseCommandInput,
  type CommandSuggestion,
} from "../lib/command-parser"
import { getCommandGuideExamples } from "../lib/command-guide"
import { getInitialCommandInput, getMobilePrimaryActions } from "../lib/mobile-ui"
import { createRelayTransport, type RelayTransport } from "../lib/relay-transport"
import { deriveRelayUrl } from "../lib/relay-url"

type ConnectionState = "connecting" | "online" | "offline"

type PendingIncomingTransfer = {
  meta: RelayFileMeta
  chunks: Array<Uint8Array | undefined>
  received: number
}

type SessionRole = "creator" | "joiner" | null

const webAgentCapabilities: AgentCapability[] = [
  { id: "chat", version: 1 },
  { id: "file-transfer", version: 1 },
  { id: "model-context", version: 1, permissions: ["read"] },
  { id: "consent-request", version: 1 },
]

const logoLines = [
  "██████╗ ██████╗ ███████╗ █████╗  ██████╗██╗  ██╗",
  "██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔════╝██║  ██║",
  "██████╔╝██████╔╝█████╗  ███████║██║     ███████║",
  "██╔═══╝ ██╔══██╗██╔══╝  ██╔══██║██║     ██╔══██║",
  "██║     ██║  ██║███████╗██║  ██║╚██████╗██║  ██║",
  "╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝",
]

function getRelayUrl(): string {
  return deriveRelayUrl({
    explicit: import.meta.env.VITE_RELAY_URL,
    search: window.location.search,
    protocol: window.location.protocol,
    hostname: window.location.hostname,
    host: window.location.host,
    port: window.location.port,
  })
}

function makeId(): string {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Math.random().toString(36).slice(2, 10)
}

async function copyText(value: string, onSuccess: () => void, onFailure: () => void) {
  try {
    await navigator.clipboard.writeText(value)
    onSuccess()
  } catch {
    onFailure()
  }
}

function downloadBlob(url: string, filename: string) {
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
}

function revokeObjectUrl(url: string | undefined, bucket: string[]) {
  if (!url) return
  URL.revokeObjectURL(url)
  const index = bucket.indexOf(url)
  if (index >= 0) bucket.splice(index, 1)
}

function trimPeerId(value: string | null): string {
  if (!value) return "waiting"
  return value.length > 12 ? `${value.slice(0, 6)}...${value.slice(-4)}` : value
}

function createOutgoingTransfer(id: string, name: string, size: number): TransferState {
  return {
    id,
    name,
    size,
    direction: "send",
    status: "pending",
    progress: 0,
    detail: "等待发送",
  }
}

function createIncomingTransfer(id: string, name: string, size: number): TransferState {
  return {
    id,
    name,
    size,
    direction: "receive",
    status: "pending",
    progress: 0,
    detail: "等待接收",
  }
}

function patchTransferList(
  current: TransferState[],
  id: string,
  patch: Partial<TransferState>,
  seed?: TransferState,
): TransferState[] {
  const index = current.findIndex((transfer) => transfer.id === id)
  if (index === -1) {
    if (!seed) return current
    return [{ ...seed, ...patch, id }, ...current]
  }

  const next = current.slice()
  next[index] = { ...next[index], ...patch, id }
  return next
}

function removeTransfer(current: TransferState[], id: string): TransferState[] {
  return current.filter((transfer) => transfer.id !== id)
}

function createWebAgentDescriptor(peerId: string | null): AgentDescriptor {
  return {
    nodeId: peerId ? `web-${peerId}` : "web-pending",
    kind: "runtime",
    displayName: "FAST P2P Web",
    capabilities: webAgentCapabilities,
    metadata: {
      surface: "web",
    },
  }
}

export function HomePage() {
  const relayUrl = useMemo(() => getRelayUrl(), [])
  const initialInvite = useMemo(() => {
    return parseRelayInvite({
      search: window.location.search,
      hash: window.location.hash,
    })
  }, [])
  const initialRoom = initialInvite.roomCode

  const [connection, setConnection] = useState<ConnectionState>("connecting")
  const [roomCode, setRoomCode] = useState("")
  const [sessionSecret, setSessionSecret] = useState(initialInvite.sessionSecret ?? "")
  const [peerId, setPeerId] = useState<string | null>(null)
  const [peerConnected, setPeerConnected] = useState(false)
  const [selfPeerId, setSelfPeerId] = useState<string | null>(null)
  const [sessionRole, setSessionRole] = useState<SessionRole>(null)
  const [transfers, setTransfers] = useState<TransferState[]>([])
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const [commandInput, setCommandInput] = useState(getInitialCommandInput(initialRoom))
  const [commandFocused, setCommandFocused] = useState(false)
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0)
  const [latestEvent, setLatestEvent] = useState("输入“创建房间”开始")
  const [qrCodeUrl, setQrCodeUrl] = useState("")
  const [hasActivatedFlow, setHasActivatedFlow] = useState(Boolean(initialRoom))
  const [guideIndex, setGuideIndex] = useState(0)
  const [isMobileViewport, setIsMobileViewport] = useState(() => window.matchMedia("(max-width: 768px)").matches)
  const [mobileCommandOpen, setMobileCommandOpen] = useState(false)

  const transportRef = useRef<RelayTransport | null>(null)
  const keyRef = useRef<RelayKey | null>(null)
  const roomCodeRef = useRef("")
  const sessionSecretRef = useRef(initialInvite.sessionSecret ?? "")
  const selfPeerIdRef = useRef<string | null>(null)
  const sessionRoleRef = useRef<SessionRole>(null)
  const pendingCreateRef = useRef(false)
  const autoJoinRef = useRef(initialInvite)
  const objectUrlsRef = useRef<string[]>([])
  const mountedRef = useRef(true)
  const pendingIncomingRef = useRef<PendingIncomingTransfer | null>(null)
  const earlyChunksRef = useRef<{ index: number; decrypted: Uint8Array; total: number }[]>([])
  const pendingOutgoingFileRef = useRef<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const commandInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    roomCodeRef.current = roomCode
  }, [roomCode])

  useEffect(() => {
    sessionSecretRef.current = sessionSecret
  }, [sessionSecret])

  useEffect(() => {
    selfPeerIdRef.current = selfPeerId
  }, [selfPeerId])

  useEffect(() => {
    sessionRoleRef.current = sessionRole
  }, [sessionRole])

  useEffect(() => {
    const media = window.matchMedia("(max-width: 768px)")
    const update = () => setIsMobileViewport(media.matches)
    update()
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", update)
      return () => media.removeEventListener("change", update)
    }
    media.addListener(update)
    return () => media.removeListener(update)
  }, [])

  function showToast(message: string, type: ToastMessage["type"] = "info") {
    const id = makeId()
    setToasts((current) => [...current, { id, message, type }])
    window.setTimeout(() => {
      if (!mountedRef.current) return
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 2800)
  }

  function pushEvent(message: string) {
    setLatestEvent(message)
  }

  function clearSessionMeta() {
    setPeerId(null)
    setPeerConnected(false)
    setQrCodeUrl("")
    pendingIncomingRef.current = null
    earlyChunksRef.current = []
  }

  async function deriveSessionKey(room: string, _secret?: string | null) {
    // 始终使用房间码推导密钥，确保发送方和接收方密钥一致
    return deriveRelayKey(room)
  }

  async function buildQrCode(room: string, secret = sessionSecretRef.current) {
    return QRCode.toDataURL(buildRelayInviteLink(window.location.origin, room, secret), {
      margin: 1,
      width: 216,
      color: { dark: "#071018", light: "#eef2ff" },
    })
  }

  function clearSessionIdentity() {
    setSelfPeerId(null)
    setSessionRole(null)
  }

  async function sendAgentSignal(message: AgentProtocolMessage) {
    const key = keyRef.current

    try {
      return sendMessage({
        type: "signal",
        data: key ? await encryptAgentSignal(message, key) : message,
      })
    } catch (error) {
      showToast("Agent 信令加密失败", "error")
      pushEvent(`Agent 信令加密失败：${error instanceof Error ? error.message : "未知错误"}`)
      return false
    }
  }

  async function sendAgentHello(transportName = "relay") {
    const currentRoom = roomCodeRef.current
    const currentPeerId = selfPeerIdRef.current
    if (!currentRoom || !currentPeerId) return

    await sendAgentSignal(
      createAgentHello(createWebAgentDescriptor(currentPeerId), {
        sessionId: currentRoom,
        createdAt: Date.now(),
        requiredCapabilities: ["file-transfer"],
        transport: transportName,
      }),
    )
  }

  async function flushPendingOutgoingFile() {
    const pendingFile = pendingOutgoingFileRef.current
    if (!pendingFile) return
    const transport = transportRef.current
    if (!transport || transport.state !== "online") return
    if (!roomCodeRef.current || !keyRef.current || !peerConnected) return

    pendingOutgoingFileRef.current = null
    pushEvent(`正在恢复发送 ${pendingFile.name}`)
    await sendFile(pendingFile)
  }

  function sendMessage(message: RelayClientMessage) {
    const transport = transportRef.current
    if (!transport || transport.state !== "online") {
      showToast("中继尚未连接", "error")
      pushEvent("中继尚未连接")
      return false
    }

    if (transport.send(message)) {
      return true
    }

    showToast("消息发送失败", "error")
    pushEvent("消息发送失败")
    return false
  }

  function handleTransportOnline() {
    if (!mountedRef.current) return
    pushEvent("已连接到中继")

    if (pendingCreateRef.current) {
      pendingCreateRef.current = false
      void createRoom()
      return
    }

    if (autoJoinRef.current.roomCode) {
      const invite = autoJoinRef.current
      autoJoinRef.current = { roomCode: "", sessionSecret: null }
      void joinRoom(invite.roomCode, invite.sessionSecret)
      return
    }

    if (roomCodeRef.current && selfPeerIdRef.current && sessionRoleRef.current) {
      sendMessage({
        type: "reconnect",
        room: roomCodeRef.current,
        peerId: selfPeerIdRef.current,
        role: sessionRoleRef.current,
      })
      pushEvent("正在恢复房间连接")
    }
  }

  function handleTransportOffline() {
    if (!mountedRef.current) return
    setPeerConnected(false)
    setPeerId(null)
    pushEvent("中继已断开，正在重连")
  }

  async function handleRelayChunk(payload: RelayChunkPayload) {
    const key = keyRef.current
    if (!key) {
      showToast("接收失败：当前没有可用密钥", "error")
      pushEvent("接收失败：当前没有可用密钥")
      return
    }

    try {
      const decrypted = await decryptRelayChunk(payload, key)
      const meta = payload._meta ?? payload.meta ?? null

      if (meta) {
        // 初始化 pending transfer
        pendingIncomingRef.current = {
          meta,
          chunks: Array.from({ length: meta.total }),
          received: 0,
        }
        setTransfers((current) =>
          patchTransferList(
            current,
            meta.id,
            { status: "transferring", progress: 0, detail: "接收中" },
            createIncomingTransfer(meta.id, meta.name, meta.size),
          ),
        )

        // 回放提前到达的数据块
        const early = earlyChunksRef.current
        if (early.length > 0) {
          earlyChunksRef.current = []
          for (const item of early) {
            const pending = pendingIncomingRef.current
            if (!pending) break
            if (!pending.chunks[item.index]) {
              pending.chunks[item.index] = item.decrypted
              pending.received += 1
            }
          }
          // 更新进度
          if (pendingIncomingRef.current) {
            const p = pendingIncomingRef.current
            setTransfers((current) =>
              patchTransferList(current, p.meta.id, {
                status: "transferring",
                progress: p.received / p.meta.total,
                detail: `已接收 ${p.received}/${p.meta.total} 块`,
              }),
            )
          }
        }
      }

      const pending = pendingIncomingRef.current
      if (!pending) {
        // meta 还没到，暂存到缓冲区
        earlyChunksRef.current.push({
          index: payload.index,
          decrypted,
          total: payload.total,
        })
        return
      }

      if (!pending.chunks[payload.index]) {
        pending.chunks[payload.index] = decrypted
        pending.received += 1
      }

      setTransfers((current) =>
        patchTransferList(current, pending.meta.id, {
          status: "transferring",
          progress: pending.received / pending.meta.total,
          detail: `已接收 ${pending.received}/${pending.meta.total} 块`,
        }),
      )
      pushEvent(`正在接收 ${pending.meta.name}`)
    } catch (error) {
      console.error("[handleRelayChunk]", error)
      const pending = pendingIncomingRef.current
      if (pending) {
        setTransfers((current) =>
          patchTransferList(current, pending.meta.id, {
            status: "error",
            detail: "解密失败",
          }),
        )
      }
      showToast("数据块解密失败", "error")
      pushEvent(`解密失败：${error instanceof Error ? error.message : "未知错误"}`)
    }
  }

  async function finishIncomingTransfer(hash: string) {
    const pending = pendingIncomingRef.current
    if (!pending) return
    pendingIncomingRef.current = null

    try {
      if (pending.chunks.some((chunk) => !chunk)) {
        setTransfers((current) =>
          patchTransferList(current, pending.meta.id, {
            status: "error",
            detail: "缺少数据块",
          }),
        )
        showToast(`接收失败：${pending.meta.name}`, "error")
        pushEvent(`接收失败：${pending.meta.name}`)
        return
      }

      const blobParts: BlobPart[] = (pending.chunks as Uint8Array[]).map((chunk) => new Uint8Array(chunk))
      const blob = new Blob(blobParts)
      const expectedHash = hash || pending.meta.hash || ""

      if (expectedHash) {
        const actualHash = await sha256Hex(await blob.arrayBuffer())
        if (actualHash !== expectedHash) {
          setTransfers((current) =>
            patchTransferList(current, pending.meta.id, {
              status: "error",
              detail: "校验失败",
            }),
          )
          showToast(`校验失败：${pending.meta.name}`, "error")
          pushEvent(`校验失败：${pending.meta.name}`)
          return
        }
      }

      const url = URL.createObjectURL(blob)
      objectUrlsRef.current.push(url)
      setTransfers((current) =>
        patchTransferList(current, pending.meta.id, {
          status: "done",
          progress: 1,
          detail: "接收完成",
          downloadUrl: url,
        }),
      )
      showToast(`已接收 ${pending.meta.name}`, "success")
      pushEvent(`已接收 ${pending.meta.name}`)
    } catch (error) {
      setTransfers((current) =>
        patchTransferList(current, pending.meta.id, {
          status: "error",
          detail: "接收失败",
        }),
      )
      showToast(`接收失败：${pending.meta.name}`, "error")
      pushEvent(`接收失败：${error instanceof Error ? error.message : "未知错误"}`)
    }
  }

  async function handleServerMessage(message: RelayServerMessage) {
    try {
      switch (message.type) {
        case "created": {
          const secret = sessionSecretRef.current || createRelaySessionSecret()
          sessionSecretRef.current = secret
          setSessionSecret(secret)
          keyRef.current = await deriveSessionKey(message.room, secret)
          setRoomCode(message.room)
          setSelfPeerId(message.peerId)
          setSessionRole("creator")
          clearSessionMeta()
          setQrCodeUrl(await buildQrCode(message.room, secret))
          showToast(`房间已创建：${message.room}`, "success")
          pushEvent(`房间已创建：${message.room}`)
          break
        }

        case "joined":
          keyRef.current = await deriveSessionKey(message.room)
          setRoomCode(message.room)
          setSelfPeerId(message.peerId)
          setSessionRole("joiner")
          setPeerId(message.peer)
          setPeerConnected(Boolean(message.peer))
          setQrCodeUrl("")
          showToast(`已加入房间：${message.room}`, "success")
          pushEvent(`已加入房间：${message.room}`)
          if (message.peer) {
            window.setTimeout(() => void sendAgentHello(), 0)
          }
          await flushPendingOutgoingFile()
          break

        case "reconnected":
          if (!keyRef.current) {
            keyRef.current = await deriveSessionKey(message.room)
          }
          setRoomCode(message.room)
          setSelfPeerId(message.peerId)
          setSessionRole(message.role)
          setPeerId(message.peer)
          setPeerConnected(Boolean(message.peer))
          if (message.role === "creator") {
            setQrCodeUrl(await buildQrCode(message.room))
          } else {
            setQrCodeUrl("")
          }
          showToast("房间连接已恢复", "success")
          pushEvent(`房间连接已恢复：${message.room}`)
          if (message.peer) {
            window.setTimeout(() => void sendAgentHello(), 0)
          }
          await flushPendingOutgoingFile()
          break

        case "peer_joined":
          setPeerId(message.peerId)
          setPeerConnected(true)
          showToast("对端已接入，可以发送文件", "success")
          pushEvent(`对端已接入：${message.peerId}`)
          window.setTimeout(() => void sendAgentHello(), 0)
          await flushPendingOutgoingFile()
          break

        case "peer_leave":
          setPeerConnected(false)
          setPeerId(null)
          showToast("对端已断开连接", "info")
          pushEvent("对端已离开房间")
          break

        case "relay":
          await handleRelayChunk(message.data)
          break

        case "done":
          await finishIncomingTransfer(message.hash)
          break

        case "error":
          showToast(message.message, "error")
          pushEvent(message.message)
          break

        case "signal":
          await handleAgentSignal(message.data)
          break
      }
    } catch (error) {
      console.error("[handleServerMessage]", error)
      showToast("处理中继消息失败", "error")
      pushEvent(`处理中继消息失败：${error instanceof Error ? error.message : "未知错误"}`)
    }
  }

  async function parseAgentSignal(data: unknown): Promise<AgentProtocolMessage | null> {
    if (isAgentProtocolMessage(data)) return data
    if (!isEncryptedAgentSignal(data)) return null

    const key = keyRef.current
    if (!key) {
      throw new Error("Missing session key for encrypted agent signal")
    }

    return decryptAgentSignal(data, key)
  }

  async function handleAgentSignal(data: unknown) {
    const message = await parseAgentSignal(data)
    if (!message) return

    if (message.type === "agent/hello") {
      const currentRoom = roomCodeRef.current
      const currentPeerId = selfPeerIdRef.current
      if (!currentRoom || !currentPeerId) return

      const negotiation = negotiateAgentCapabilities(
        webAgentCapabilities,
        message.from.capabilities,
        message.offer.requiredCapabilities,
      )

      if (!negotiation.accepted) {
        await sendAgentSignal(createAgentReject(message.offer.sessionId, "Missing required capabilities", negotiation.missingRequired))
        pushEvent("对端能力协商失败")
        return
      }

      await sendAgentSignal(createAgentAccept(createWebAgentDescriptor(currentPeerId), message.offer.sessionId, negotiation.common))
      pushEvent(`已协商能力：${negotiation.common.map((capability) => capability.id).join(", ")}`)
      return
    }

    if (message.type === "agent/accept") {
      pushEvent(`对端接受能力：${message.capabilities.map((capability) => capability.id).join(", ")}`)
      return
    }

    if (message.type === "agent/reject") {
      showToast(`能力协商失败：${message.reason}`, "error")
      pushEvent(`能力协商失败：${message.reason}`)
    }
  }

  async function createRoom() {
    if (!transportRef.current || transportRef.current.state !== "online") {
      pendingCreateRef.current = true
      transportRef.current?.connect()
      return
    }

    if (roomCodeRef.current) {
      sendMessage({ type: "leave" })
    }

    keyRef.current = null
    const secret = createRelaySessionSecret()
    sessionSecretRef.current = secret
    setSessionSecret(secret)
    setRoomCode("")
    clearSessionMeta()
    clearSessionIdentity()
    if (sendMessage({ type: "create" })) {
      pushEvent("正在创建房间")
    }
  }

  async function joinRoom(value: string, nextSessionSecret?: string | null) {
    const normalized = normalizeRoomCode(value)
    if (!normalized) {
      showToast("请输入房间码", "error")
      return
    }

    if (!transportRef.current || transportRef.current.state !== "online") {
      autoJoinRef.current = {
        roomCode: normalized,
        sessionSecret: nextSessionSecret ?? null,
      }
      transportRef.current?.connect()
      return
    }

    if (roomCodeRef.current) {
      sendMessage({ type: "leave" })
    }

    try {
      const normalizedSecret = (nextSessionSecret ?? "").trim().toUpperCase()
      sessionSecretRef.current = normalizedSecret
      setSessionSecret(normalizedSecret)
      keyRef.current = await deriveSessionKey(normalized, normalizedSecret)
      setRoomCode("")
      clearSessionMeta()
      clearSessionIdentity()
      if (sendMessage({ type: "join", room: normalized })) {
        pushEvent(`正在加入房间：${normalized}`)
      }
    } catch (error) {
      showToast("加入房间失败", "error")
      pushEvent(`加入失败：${error instanceof Error ? error.message : "未知错误"}`)
    }
  }

  function leaveRoom() {
    sendMessage({ type: "leave" })
    keyRef.current = null
    sessionSecretRef.current = ""
    setSessionSecret("")
    setRoomCode("")
    clearSessionMeta()
    clearSessionIdentity()
    pendingOutgoingFileRef.current = null
    pushEvent("已离开房间")
  }

  async function sendFile(file: File) {
    const transport = transportRef.current
    const key = keyRef.current

    if (!transport || transport.state !== "online") {
      if (roomCode && key) {
        pendingOutgoingFileRef.current = file
        showToast("连接恢复后会自动继续发送", "info")
        pushEvent(`已暂存 ${file.name}，等待重连`)
      } else {
        showToast("中继未连接", "error")
        pushEvent("中继未连接")
      }
      return
    }

    if (!roomCode || !key) {
      showToast("请先创建或加入房间", "error")
      pushEvent("请先创建或加入房间")
      return
    }

    if (!peerConnected) {
      showToast("请等待对端接入房间", "error")
      pushEvent("请等待对端接入房间")
      return
    }

    const id = makeId()

    setTransfers((current) =>
      patchTransferList(current, id, { status: "pending", progress: 0, detail: "准备发送" }, createOutgoingTransfer(id, file.name, file.size)),
    )

    try {
      const buffer = await file.arrayBuffer()
      const hash = await sha256Hex(buffer)
      const total = Math.max(1, Math.ceil(buffer.byteLength / RELAY_CHUNK_SIZE))

      for (let index = 0; index < total; index++) {
        if (transport.state !== "online") {
          throw new Error("连接已中断")
        }

        const start = index * RELAY_CHUNK_SIZE
        const end = Math.min(start + RELAY_CHUNK_SIZE, buffer.byteLength)
        const chunk = new Uint8Array(buffer.slice(start, end))
        const encrypted = await encryptRelayChunk(chunk, key)
        const meta: RelayFileMeta | null =
          index === 0
            ? {
                id,
                name: file.name,
                size: file.size,
                total,
                hash,
              }
            : null

        if (
          !transport.send({
            type: "relay",
            data: {
              ...encrypted,
              index,
              total,
              _meta: meta,
            },
          })
        ) {
          throw new Error("连接已中断")
        }

        setTransfers((current) =>
          patchTransferList(current, id, {
            status: "transferring",
            progress: (index + 1) / total,
            detail: `已发送 ${index + 1}/${total} 块`,
          }),
        )

        await new Promise((resolve) => window.setTimeout(resolve, 0))
      }

      if (!transport.send({ type: "done", hash })) {
        throw new Error("连接已中断")
      }
      setTransfers((current) =>
        patchTransferList(current, id, {
          status: "done",
          progress: 1,
          detail: "发送完成",
        }),
      )
      showToast(`已发送 ${file.name}`, "success")
      pushEvent(`已发送 ${file.name}`)
    } catch (error) {
      const detail = error instanceof Error ? error.message : "未知错误"
      if (detail.includes("连接已中断")) {
        pendingOutgoingFileRef.current = file
        showToast(`连接中断，恢复后继续发送 ${file.name}`, "info")
        pushEvent(`连接中断，等待恢复后继续发送 ${file.name}`)
        return
      }
      setTransfers((current) =>
        patchTransferList(current, id, {
          status: "error",
          detail: "发送失败",
        }),
      )
      showToast(`发送失败：${file.name}`, "error")
      pushEvent(`发送失败：${detail}`)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    const transport = createRelayTransport({ url: relayUrl })
    transportRef.current = transport

    const unsubscribeState = transport.on("state", (state) => {
      if (!mountedRef.current) return
      setConnection(state)

      if (state === "online") {
        handleTransportOnline()
        return
      }

      if (state === "offline") {
        handleTransportOffline()
      }
    })

    const unsubscribeMessage = transport.on("message", (message: RelayServerMessage) => {
      void handleServerMessage(message)
    })

    const unsubscribeError = transport.on("error", (error) => {
      if (!mountedRef.current) return
      showToast("中继连接异常，正在自动重试", "error")
      pushEvent(error.message === "Invalid relay payload" ? "收到无法解析的中继消息" : "中继连接异常")
    })

    transport.connect()

    return () => {
      mountedRef.current = false
      unsubscribeState()
      unsubscribeMessage()
      unsubscribeError()
      transport.disconnect()
      transportRef.current = null
      for (const url of objectUrlsRef.current) {
        URL.revokeObjectURL(url)
      }
    }
  }, [relayUrl])

  useEffect(() => {
    const url = new URL(window.location.href)
    if (roomCode) url.searchParams.set("room", roomCode)
    else url.searchParams.delete("room")
    if (roomCode && sessionSecret) url.hash = `key=${sessionSecret}`
    else url.hash = ""
    window.history.replaceState({}, "", url)
  }, [roomCode, sessionSecret])

  useEffect(() => {
    setActiveSuggestionIndex(0)
  }, [commandInput, roomCode, peerConnected])

  const guideExamples = useMemo(() => getCommandGuideExamples(Boolean(roomCode)), [roomCode])

  useEffect(() => {
    setGuideIndex(0)
  }, [roomCode])

  useEffect(() => {
    if (!isMobileViewport) {
      setMobileCommandOpen(false)
      return
    }

    if (!roomCode) {
      setMobileCommandOpen(false)
    }
  }, [isMobileViewport, roomCode])

  useEffect(() => {
    if (roomCode || hasActivatedFlow) return
    const timer = window.setInterval(() => {
      setGuideIndex((current) => (current + 1) % guideExamples.length)
    }, 2200)
    return () => window.clearInterval(timer)
  }, [guideExamples.length, hasActivatedFlow, roomCode])

  const roomLink = roomCode ? buildRelayInviteLink(window.location.origin, roomCode, sessionSecret) : ""
  const joinToken = roomCode ? buildRelayJoinToken(roomCode, sessionSecret) : ""
  const mobileActions = getMobilePrimaryActions({
    roomCode,
    hasRoomLink: Boolean(roomLink),
    peerConnected,
  })
  const suggestions = getCommandSuggestions(commandInput, {
    roomCode,
    peerConnected,
    hasRoomLink: Boolean(roomLink),
  })
  const activeSuggestion = suggestions[activeSuggestionIndex] ?? null
  const suggestionVisible =
    commandFocused &&
    suggestions.length > 0 &&
    (commandInput.trim().length > 0 || (!roomCode && !peerConnected))

  async function executeCommand(rawValue: string) {
    const parsed = parseCommandInput(rawValue, {
      roomCode,
      peerConnected,
      hasRoomLink: Boolean(roomLink),
    })

    setCommandFocused(false)
    if (rawValue.trim().length > 0) setHasActivatedFlow(true)

    switch (parsed.kind) {
      case "create-room":
        await createRoom()
        break
      case "join-room":
        await joinRoom(parsed.roomCode, parsed.sessionSecret)
        break
      case "copy-link":
        await copyText(
          roomLink,
          () => {
            showToast("分享链接已复制", "success")
            pushEvent("分享链接已复制")
          },
          () => {
            showToast("复制分享链接失败", "error")
            pushEvent("复制分享链接失败")
          },
        )
        break
      case "copy-room-code":
        await copyText(
          joinToken,
          () => {
            showToast("加入码已复制", "success")
            pushEvent("加入码已复制")
          },
          () => {
            showToast("复制加入码失败", "error")
            pushEvent("复制加入码失败")
          },
        )
        break
      case "pick-file":
        fileInputRef.current?.click()
        pushEvent("请选择要发送的文件")
        break
      case "leave-room":
        leaveRoom()
        break
      case "invalid":
        showToast(parsed.reason, "error")
        pushEvent(parsed.reason)
        break
    }
  }

  function applySuggestion(suggestion: CommandSuggestion) {
    if (suggestion.behavior === "execute") {
      void executeCommand(suggestion.command)
      setCommandInput("")
      commandInputRef.current?.blur()
      return
    }

    setCommandInput(suggestion.command)
    setMobileCommandOpen(true)
    window.requestAnimationFrame(() => commandInputRef.current?.focus())
  }

  const connectionLabel =
    connection === "online" ? "relay online" : connection === "connecting" ? "relay connecting" : "relay offline"
  const commandDocked = hasActivatedFlow || Boolean(roomCode)
  const showCommandShell = !isMobileViewport || mobileCommandOpen

  return (
    <main className="stage-shell">
      <ToastContainer toasts={toasts} />

      <motion.header
        className="stage-topline"
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24, ease: "easeOut" }}
      >
        <div className="stage-chip">
          <span className={`stage-dot stage-dot-${connection}`} />
          <span>{connectionLabel}</span>
        </div>
        <div className="stage-chip">
          <span>peer</span>
          <span>{trimPeerId(peerId)}</span>
        </div>
        <div className="stage-chip">
          <span>latest</span>
          <span>{latestEvent}</span>
        </div>
      </motion.header>

      <section className="stage-main">
        <motion.div
          className="logo-stage"
          initial={{ opacity: 0, y: 16, filter: "blur(10px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="logo-meta">
            <span>FAST P2P</span>
            <span>{roomCode ? `ROOM ${roomCode}` : "READY"}</span>
          </div>
          <pre className="logo-mark" aria-label="FAST P2P logo">
            {logoLines.join("\n")}
          </pre>
        </motion.div>

        <AnimatePresence initial={false}>
          {roomCode ? (
            <motion.section
              className="session-stage"
              key="session"
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 18 }}
              transition={{ duration: 0.24, ease: "easeOut" }}
            >
              <div className={`session-strip${sessionRole === "joiner" ? " session-strip-joiner" : ""}`}>
                <div className="session-card">
                  <span className="session-label">room</span>
                  <strong>{roomCode}</strong>
                  <button className="session-action" onClick={() => void executeCommand("复制房间码")}>
                    复制加入码
                  </button>
                </div>

                <div className="session-card">
                  <span className="session-label">link</span>
                  <strong className="session-clip">{roomLink || "waiting"}</strong>
                  <button className="session-action" onClick={() => void executeCommand("复制链接")} disabled={!roomLink}>
                    复制链接
                  </button>
                </div>

                {sessionRole !== "joiner" ? (
                  <div className="session-card session-card-qr">
                    <span className="session-label">join</span>
                    <div className="session-qr-block">
                      {qrCodeUrl ? (
                        <img src={qrCodeUrl} alt="房间二维码" className="session-qr" />
                      ) : (
                        <div className="session-qr-placeholder" />
                      )}
                    </div>
                    <div className="session-qr-copy">
                      <strong>扫码加入</strong>
                      <span>或把链接发到另一台设备</span>
                    </div>
                  </div>
                ) : null}
              </div>

              <motion.div
                className="session-transfers"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22, delay: 0.05, ease: "easeOut" }}
              >
                <TransferList
                  transfers={transfers}
                  onDownload={downloadBlob}
                  onRemove={(id) => {
                    setTransfers((current) => {
                      const target = current.find((transfer) => transfer.id === id)
                      revokeObjectUrl(target?.downloadUrl, objectUrlsRef.current)
                      return removeTransfer(current, id)
                    })
                    showToast("传输记录已移除", "info")
                    pushEvent("传输记录已移除")
                  }}
                />
              </motion.div>
            </motion.section>
          ) : null}
        </AnimatePresence>
      </section>

      <motion.section
        className={`command-stage${commandDocked ? " is-docked" : " is-centered"}`}
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1, ease: "easeOut" }}
        layout
      >
        <AnimatePresence>
          {suggestionVisible ? (
            <motion.div
              className="command-suggestions"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              {suggestions.slice(0, 5).map((suggestion, index) => (
                <button
                  key={suggestion.label}
                  className={`command-suggestion${index === activeSuggestionIndex ? " is-active" : ""}`}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applySuggestion(suggestion)}
                >
                  <span>{suggestion.label}</span>
                  <small>{suggestion.hint}</small>
                </button>
              ))}
            </motion.div>
          ) : null}
        </AnimatePresence>

        <AnimatePresence initial={false}>
          {!roomCode && !hasActivatedFlow ? (
            <motion.div
              key={guideExamples[guideIndex]}
              className="command-guide"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
            >
              <span className="command-guide-label">try</span>
              <span className="command-guide-value">$ {guideExamples[guideIndex]}</span>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {isMobileViewport ? (
          <div className="mobile-action-bar">
            {mobileActions.map((action) => (
              <button
                key={action.id}
                className="mobile-action-button"
                onClick={() => {
                  if (action.id === "create-room") {
                    void executeCommand("创建房间")
                    return
                  }
                  if (action.id === "join-room") {
                    setCommandInput("加入 ")
                    setMobileCommandOpen(true)
                    window.requestAnimationFrame(() => commandInputRef.current?.focus())
                    return
                  }
                  if (action.id === "pick-file") {
                    void executeCommand("发送文件")
                    return
                  }
                  if (action.id === "copy-link") {
                    void executeCommand("复制链接")
                    return
                  }
                  if (action.id === "leave-room") {
                    void executeCommand("离开房间")
                  }
                }}
              >
                {action.label}
              </button>
            ))}
            <button
              className={`mobile-action-button mobile-action-button-command${mobileCommandOpen ? " is-open" : ""}`}
              onClick={() => {
                setMobileCommandOpen((current) => !current)
                if (!mobileCommandOpen) {
                  window.requestAnimationFrame(() => commandInputRef.current?.focus())
                } else {
                  commandInputRef.current?.blur()
                }
              }}
            >
              {mobileCommandOpen ? "收起命令" : "命令"}
            </button>
          </div>
        ) : null}

        {showCommandShell ? (
          <div className="command-shell">
            <span className="command-prefix">$</span>
            <input
              ref={commandInputRef}
              className="command-input"
              value={commandInput}
              onFocus={() => setCommandFocused(true)}
              onBlur={() => window.setTimeout(() => setCommandFocused(false), 100)}
              onChange={(event) => setCommandInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown" && suggestions.length > 0) {
                  event.preventDefault()
                  setActiveSuggestionIndex((current) => (current + 1) % Math.min(suggestions.length, 5))
                  return
                }

                if (event.key === "ArrowUp" && suggestions.length > 0) {
                  event.preventDefault()
                  setActiveSuggestionIndex((current) => (current - 1 + Math.min(suggestions.length, 5)) % Math.min(suggestions.length, 5))
                  return
                }

                if (event.key === "Tab" && activeSuggestion) {
                  event.preventDefault()
                  applySuggestion(activeSuggestion)
                  return
                }

                if (event.key === "Enter") {
                  event.preventDefault()
                  if (activeSuggestion && commandInput.trim().length === 0 && activeSuggestion.behavior === "prefill") {
                    applySuggestion(activeSuggestion)
                    return
                  }
                  const value = activeSuggestion && commandInput.trim().length === 0 ? activeSuggestion.command : commandInput
                  void executeCommand(value)
                  setCommandInput("")
                  commandInputRef.current?.blur()
                  if (isMobileViewport) setMobileCommandOpen(false)
                }
              }}
              spellCheck={false}
              autoCapitalize="off"
              autoComplete="off"
              placeholder={roomCode ? "输入“发送文件” / “复制链接” / “离开房间”" : "输入“创建房间”或“加入 ROOM01”"}
              aria-label="命令输入框"
            />
          </div>
        ) : null}

        <input
          ref={fileInputRef}
          type="file"
          className="hidden-file-input"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) {
              void sendFile(file)
              event.currentTarget.value = ""
            }
          }}
          aria-hidden="true"
          tabIndex={-1}
        />
      </motion.section>
    </main>
  )
}
