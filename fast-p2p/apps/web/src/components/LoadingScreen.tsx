import { useState, useEffect, useRef, type TransitionEvent } from "react"

type LoadingScreenProps = {
  minDuration?: number
  onLoaded?: () => void
  caption?: string
}

export function LoadingScreen({
  minDuration = 2000,
  onLoaded,
  caption = "滚轮推进场景，页面本身不做原生上下滚动",
}: LoadingScreenProps) {
  const [progress, setProgress] = useState(0)
  const [isVisible, setIsVisible] = useState(true)
  const onLoadedRef = useRef(onLoaded)
  const progressTimerRef = useRef<number | null>(null)
  const exitTimerRef = useRef<number | null>(null)
  const fallbackTimerRef = useRef<number | null>(null)
  const hasCompletedRef = useRef(false)

  useEffect(() => {
    onLoadedRef.current = onLoaded
  }, [onLoaded])

  useEffect(() => {
    const startTime = Date.now()

    const clearTimers = () => {
      if (progressTimerRef.current !== null) {
        window.clearTimeout(progressTimerRef.current)
        progressTimerRef.current = null
      }
      if (exitTimerRef.current !== null) {
        window.clearTimeout(exitTimerRef.current)
        exitTimerRef.current = null
      }
      if (fallbackTimerRef.current !== null) {
        window.clearTimeout(fallbackTimerRef.current)
        fallbackTimerRef.current = null
      }
    }

    const updateProgress = () => {
      const elapsed = Date.now() - startTime
      const newProgress = Math.min(100, (elapsed / minDuration) * 100)
      setProgress(newProgress)

      if (newProgress < 100) {
        progressTimerRef.current = window.setTimeout(updateProgress, 16)
      } else {
        exitTimerRef.current = window.setTimeout(() => {
          setIsVisible(false)
        }, 120)
      }
    }

    progressTimerRef.current = window.setTimeout(updateProgress, 16)

    return clearTimers
  }, [minDuration])

  useEffect(() => {
    if (isVisible) return

    fallbackTimerRef.current = window.setTimeout(() => {
      if (!hasCompletedRef.current) {
        hasCompletedRef.current = true
        onLoadedRef.current?.()
      }
    }, 700)

    return () => {
      if (fallbackTimerRef.current !== null) {
        window.clearTimeout(fallbackTimerRef.current)
        fallbackTimerRef.current = null
      }
    }
  }, [isVisible])

  const handleTransitionEnd = (event: TransitionEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget || event.propertyName !== "opacity" || isVisible) return
    if (fallbackTimerRef.current !== null) {
      window.clearTimeout(fallbackTimerRef.current)
      fallbackTimerRef.current = null
    }
    if (!hasCompletedRef.current) {
      hasCompletedRef.current = true
      onLoadedRef.current?.()
    }
  }

  const circumference = 2 * Math.PI * 50
  const strokeDashoffset = circumference - (progress / 100) * circumference

  return (
    <div
      className={`loading-screen ${!isVisible ? "hidden" : ""}`}
      role="progressbar"
      aria-valuenow={Math.round(progress)}
      aria-valuemin={0}
      aria-valuemax={100}
      onTransitionEnd={handleTransitionEnd}
    >
      <div className="loading-content">
        <div className="loading-kicker">端到端加密传输界面</div>
        <div className="loading-logo">PREACH</div>
        
        <div className="loading-progress-ring">
          <svg width="120" height="120" viewBox="0 0 120 120">
            <circle className="ring-bg" cx="60" cy="60" r="50" />
            <circle 
              className="ring-progress" 
              cx="60" 
              cy="60" 
              r="50"
              style={{ strokeDashoffset }}
            />
          </svg>
          <div className="loading-percent">{Math.round(progress)}%</div>
        </div>
        <div className="loading-caption">{caption}</div>
      </div>
    </div>
  )
}

