import type {
  ManagedTransport,
  RelayClientMessage,
  RelayServerMessage,
  TransportConnectionState,
  TransportEventMap,
} from "@fast-p2p/shared"

const CONNECTING_STATE = 0
const OPEN_STATE = 1

type SocketMessageEvent = {
  data: unknown
}

export type RelayTransportSocket = {
  readyState: number
  onopen: ((event?: Event) => void) | null
  onclose: ((event?: CloseEvent) => void) | null
  onerror: ((event?: Event) => void) | null
  onmessage: ((event: SocketMessageEvent) => void) | null
  send(data: string): void
  close(): void
}

type RelayTransportOptions = {
  url: string
  reconnectDelay?: number
  socketFactory?: (url: string) => RelayTransportSocket
}

export type RelayTransport = ManagedTransport<RelayClientMessage, RelayServerMessage>

export function createRelayTransport(options: RelayTransportOptions): RelayTransport {
  const reconnectDelay = options.reconnectDelay ?? 2200
  const socketFactory = options.socketFactory ?? ((url: string) => new WebSocket(url) as RelayTransportSocket)
  const listeners: {
    [TEvent in keyof TransportEventMap<RelayServerMessage>]: Set<TransportEventMap<RelayServerMessage>[TEvent]>
  } = {
    state: new Set(),
    message: new Set(),
    error: new Set(),
  }

  let state: TransportConnectionState = "offline"
  let socket: RelayTransportSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let closedByClient = false

  function emit<TEvent extends keyof TransportEventMap<RelayServerMessage>>(
    event: TEvent,
    payload: Parameters<TransportEventMap<RelayServerMessage>[TEvent]>[0],
  ) {
    for (const listener of listeners[event]) {
      listener(payload as never)
    }
  }

  function setState(nextState: TransportConnectionState) {
    if (state === nextState) return
    state = nextState
    emit("state", nextState)
  }

  function clearReconnectTimer() {
    if (reconnectTimer === null) return
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  function scheduleReconnect() {
    if (closedByClient || reconnectTimer !== null) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, reconnectDelay)
  }

  function connect() {
    if (socket && (socket.readyState === OPEN_STATE || socket.readyState === CONNECTING_STATE)) return

    clearReconnectTimer()
    closedByClient = false
    setState("connecting")

    const nextSocket = socketFactory(options.url)
    socket = nextSocket

    nextSocket.onopen = () => {
      if (socket !== nextSocket) return
      setState("online")
    }

    nextSocket.onclose = () => {
      if (socket === nextSocket) {
        socket = null
      }
      setState("offline")
      scheduleReconnect()
    }

    nextSocket.onerror = () => {
      emit("error", new Error("WebSocket transport error"))
    }

    nextSocket.onmessage = (event: SocketMessageEvent) => {
      if (typeof event.data !== "string") return

      try {
        emit("message", JSON.parse(event.data) as RelayServerMessage)
      } catch {
        emit("error", new Error("Invalid relay payload"))
      }
    }
  }

  function disconnect() {
    closedByClient = true
    clearReconnectTimer()

    if (!socket) {
      setState("offline")
      return
    }

    const activeSocket = socket
    socket = null
    activeSocket.close()
    setState("offline")
  }

  function send(message: RelayClientMessage): boolean {
    if (!socket || socket.readyState !== OPEN_STATE) {
      return false
    }

    try {
      socket.send(JSON.stringify(message))
      return true
    } catch (error) {
      emit("error", error instanceof Error ? error : new Error("Failed to send relay message"))
      return false
    }
  }

  return {
    get state() {
      return state
    },
    connect,
    disconnect,
    send,
    on(event, listener) {
      listeners[event].add(listener as never)
      return () => {
        listeners[event].delete(listener as never)
      }
    },
  }
}
