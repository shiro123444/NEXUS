type ConnectionState = "connecting" | "online" | "offline"

type StatusRailProps = {
  connection: ConnectionState
  stageLabel: string
  roomCode: string
}

export function StatusRail({ connection, stageLabel, roomCode }: StatusRailProps) {
  const connectionLabel =
    connection === "online" ? "在线" : connection === "connecting" ? "连接中" : "离线"
  const connectionTone =
    connection === "online"
      ? "status-dot online"
      : connection === "connecting"
        ? "status-dot waiting"
        : "status-dot offline"

  return (
    <div className="status-rail" role="status" aria-live="polite" aria-label="连接状态">
      <span className={connectionTone} aria-hidden="true" />
      <span>{connectionLabel}</span>
      <span className="rail-divider" />
      <span>{stageLabel}</span>
      {roomCode ? (
        <>
          <span className="rail-meta">{roomCode}</span>
          <span className="rail-divider" />
          <span className="security-badge" title="端到端加密" aria-label="当前连接已加密">
            已加密
          </span>
        </>
      ) : null}
    </div>
  )
}
