import { formatBytes } from "@fast-p2p/shared"

type TransferState = {
  id: string
  name: string
  size: number
  direction: "send" | "receive"
  status: "pending" | "transferring" | "done" | "error"
  progress: number
  detail?: string
  downloadUrl?: string
}

type TransferItemProps = {
  transfer: TransferState
  onDownload: (url: string, name: string) => void
  onRemove: (id: string) => void
}

export function TransferItem({ transfer, onDownload, onRemove }: TransferItemProps) {
  return (
    <div className="transfer-item" key={transfer.id}>
      <div className="transfer-head">
        <div>
          <strong>{transfer.name}</strong>
          <span>{formatBytes(transfer.size)}</span>
        </div>
        <div className={`badge badge-${transfer.status}`}>
          {transfer.direction === "send" ? "发送" : "接收"}
        </div>
      </div>

      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={Math.round(transfer.progress * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${transfer.name} 的传输进度`}
      >
        <div className="progress-fill" style={{ width: `${Math.round(transfer.progress * 100)}%` }} />
      </div>

      <div className="transfer-foot">
        <span aria-live="polite" aria-atomic="true">
          {transfer.detail ?? `${Math.round(transfer.progress * 100)}%`}
        </span>
        <div className="transfer-actions">
          {transfer.downloadUrl ? (
            <button
              className="text-button text-button-inline"
              onClick={() => onDownload(transfer.downloadUrl!, transfer.name)}
              aria-label={`下载 ${transfer.name}`}
            >
              下载
            </button>
          ) : null}
          {transfer.status === "error" ? (
            <button
              className="text-button text-button-inline text-button-error"
              onClick={() => onRemove(transfer.id)}
              aria-label={`移除失败的传输 ${transfer.name}`}
            >
              移除
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export type { TransferState }
