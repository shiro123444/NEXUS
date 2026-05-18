import { TransferItem, type TransferState } from "./TransferItem"

type TransferListProps = {
  transfers: TransferState[]
  onDownload: (url: string, name: string) => void
  onRemove: (id: string) => void
}

export function TransferList({ transfers, onDownload, onRemove }: TransferListProps) {
  if (transfers.length === 0) {
    return (
      <div className="empty-state" role="status" aria-label="当前还没有传输记录">
        <div>当前还没有传输记录</div>
      </div>
    )
  }

  return (
    <div className="transfer-list" data-native-scroll="true">
      {transfers.map((transfer) => (
        <TransferItem
          key={transfer.id}
          transfer={transfer}
          onDownload={onDownload}
          onRemove={onRemove}
        />
      ))}
    </div>
  )
}
