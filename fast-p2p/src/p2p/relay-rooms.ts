export interface RelaySocketData {
  roomCode?: string
  peerId?: string
}

export interface RelaySocket {
  data: RelaySocketData
  send(message: string): void
  close(): void
}

interface Room<TSocket extends RelaySocket> {
  creator: TSocket | null
  creatorPeerId: string
  joiner: TSocket | null
  joinerPeerId: string | null
  created: number
  cleanupTimer: ReturnType<typeof setTimeout> | null
}

function defaultGenCode(len = 6): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  let code = ""
  for (let i = 0; i < len; i++) {
    code += chars[Math.floor(Math.random() * chars.length)]
  }
  return code
}

const MAX_ROOMS = 10_000

export function createRelayRooms<TSocket extends RelaySocket>(
  genCode: (len?: number) => string = defaultGenCode,
): {
  handleMessage(socket: TSocket, msg: Record<string, unknown>): void
  handleClose(socket: TSocket): void
} {
  const rooms = new Map<string, Room<TSocket>>()

  function clearCleanup(room: Room<TSocket>) {
    if (room.cleanupTimer) {
      clearTimeout(room.cleanupTimer)
      room.cleanupTimer = null
    }
  }

  function armCleanup(roomCode: string, room: Room<TSocket>) {
    clearCleanup(room)
    room.cleanupTimer = setTimeout(() => {
      rooms.delete(roomCode)
    }, 30000)
  }

  function broadcast(room: Room<TSocket>, exclude: TSocket, msg: string) {
    if (room.creator && room.creator !== exclude) room.creator.send(msg)
    if (room.joiner && room.joiner !== exclude) room.joiner.send(msg)
  }

  return {
    handleMessage(socket: TSocket, msg: Record<string, unknown>) {
      switch (msg.type) {
        case "create": {
          if (rooms.size >= MAX_ROOMS) {
            socket.send(JSON.stringify({ type: "error", message: "Server busy, try later" }))
            return
          }

          let roomCode = genCode()
          let tries = 0
          while (rooms.has(roomCode) && tries < 10) {
            roomCode = genCode()
            tries++
          }
          if (rooms.has(roomCode)) {
            socket.send(JSON.stringify({ type: "error", message: "Failed to create room, try again" }))
            return
          }

          const peerId = genCode(4)
          rooms.set(roomCode, {
            creator: socket,
            creatorPeerId: peerId,
            joiner: null,
            joinerPeerId: null,
            created: Date.now(),
            cleanupTimer: null,
          })
          socket.data.roomCode = roomCode
          socket.data.peerId = peerId
          socket.send(JSON.stringify({ type: "created", room: roomCode, peerId }))
          break
        }

        case "join": {
          const room = rooms.get(msg.room as string)
          if (!room) {
            socket.send(JSON.stringify({ type: "error", message: "Room not found" }))
            return
          }
          if (room.joiner) {
            socket.send(JSON.stringify({ type: "error", message: "Room full" }))
            return
          }

          const roomCode = msg.room as string
          const peerId = genCode(4)
          clearCleanup(room)
          room.joiner = socket
          room.joinerPeerId = peerId
          socket.data.roomCode = roomCode
          socket.data.peerId = peerId
          socket.send(JSON.stringify({ type: "joined", room: roomCode, peerId, peer: room.creatorPeerId ?? null }))
          room.creator?.send(JSON.stringify({ type: "peer_joined", peerId }))
          break
        }

        case "reconnect": {
          const roomCode = msg.room as string
          const peerId = msg.peerId as string
          const role = msg.role as "creator" | "joiner"
          const room = rooms.get(roomCode)
          if (!room) {
            socket.send(JSON.stringify({ type: "error", message: "Room not found" }))
            return
          }

          clearCleanup(room)
          socket.data.roomCode = roomCode
          socket.data.peerId = peerId

          if (role === "creator" && room.creatorPeerId === peerId && room.creator === null) {
            room.creator = socket
            socket.send(
              JSON.stringify({
                type: "reconnected",
                room: roomCode,
                peerId,
                peer: room.joinerPeerId,
                role,
              }),
            )
            room.joiner?.send(JSON.stringify({ type: "peer_joined", peerId }))
            return
          }

          if (role === "joiner" && room.joinerPeerId === peerId && room.joiner === null) {
            room.joiner = socket
            socket.send(
              JSON.stringify({
                type: "reconnected",
                room: roomCode,
                peerId,
                peer: room.creatorPeerId,
                role,
              }),
            )
            room.creator?.send(JSON.stringify({ type: "peer_joined", peerId }))
            return
          }

          socket.send(JSON.stringify({ type: "error", message: "Reconnect rejected" }))
          break
        }

        case "relay": {
          const roomCode = socket.data.roomCode
          if (!roomCode) return
          const room = rooms.get(roomCode)
          if (!room) return
          broadcast(room, socket, JSON.stringify({ type: "relay", from: socket.data.peerId, data: msg.data }))
          break
        }

        case "signal": {
          const roomCode = socket.data.roomCode
          if (!roomCode) return
          const room = rooms.get(roomCode)
          if (!room) return
          broadcast(room, socket, JSON.stringify({ type: "signal", from: socket.data.peerId, data: msg.data }))
          break
        }

        case "done": {
          const roomCode = socket.data.roomCode
          if (!roomCode) return
          const room = rooms.get(roomCode)
          if (!room) return
          broadcast(room, socket, JSON.stringify({ type: "done", from: socket.data.peerId, hash: msg.hash ?? "" }))
          break
        }

        case "leave": {
          const roomCode = socket.data.roomCode
          if (!roomCode) return
          const room = rooms.get(roomCode)
          if (!room) return
          broadcast(room, socket, JSON.stringify({ type: "peer_leave", from: socket.data.peerId }))
          if (room.creator === socket) {
            room.creator = null
            if (room.joiner) armCleanup(roomCode, room)
            else rooms.delete(roomCode)
          } else {
            room.joiner = null
            room.joinerPeerId = null
            if (!room.creator) rooms.delete(roomCode)
          }
          socket.data.roomCode = undefined
          socket.data.peerId = undefined
          break
        }
      }
    },

    handleClose(socket: TSocket) {
      const roomCode = socket.data.roomCode
      if (!roomCode) return

      const room = rooms.get(roomCode)
      if (!room) return

      if (room.creator === socket) {
        room.creator = null
        if (room.joiner) {
          room.joiner.send(JSON.stringify({ type: "peer_leave" }))
          armCleanup(roomCode, room)
        } else {
          rooms.delete(roomCode)
        }
      } else {
        room.joiner = null
        room.joinerPeerId = null
        room.creator?.send(JSON.stringify({ type: "peer_leave" }))
        if (!room.creator) rooms.delete(roomCode)
      }
    },
  }
}
