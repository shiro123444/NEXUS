type QRCodeDisplayProps = {
  qrCodeUrl: string
}

export function QRCodeDisplay({ qrCodeUrl }: QRCodeDisplayProps) {
  const showSkeleton = !qrCodeUrl

  return (
    <div className="qr-surface">
      <span className="slab-label">二维码</span>
      {showSkeleton ? (
        <div className="qr-skeleton" aria-hidden="true" aria-busy="true" aria-label="正在生成二维码">
          {Array.from({ length: 16 }).map((_, index) => (
            <span key={index} />
          ))}
        </div>
      ) : (
        <img className="stage-qr" src={qrCodeUrl} alt="加入房间的二维码" loading="lazy" />
      )}
    </div>
  )
}
