import { useCallback, useEffect, useRef, useState } from "react"

const VIDEOS = [
  "/videos/1.mp4",
  "/videos/2.mp4",
  "/videos/3.mp4"
]

type VideoBackgroundProps = {
  scrollProgress: number
}

export function VideoBackground({ scrollProgress }: VideoBackgroundProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [loadedSet, setLoadedSet] = useState<Set<number>>(new Set())
  const [hasError, setHasError] = useState(false)
  const videoRefs = useRef<(HTMLVideoElement | null)[]>([])

  useEffect(() => {
    const newIndex = Math.min(
      Math.floor(scrollProgress * VIDEOS.length),
      VIDEOS.length - 1
    )
    if (newIndex !== activeIndex) {
      setActiveIndex(newIndex)
    }
  }, [scrollProgress, activeIndex])

  const handleVideoLoaded = useCallback((index: number) => {
    setLoadedSet(prev => new Set(prev).add(index))
    const video = videoRefs.current[index]
    if (video) {
      video.play().catch(() => {})
    }
  }, [])

  const handleVideoError = useCallback((index: number) => {
    console.warn(`Video ${index} failed to load`)
    if (index === activeIndex) {
      setHasError(true)
    }
  }, [activeIndex])

  useEffect(() => {
    if (loadedSet.size > 0 && !loadedSet.has(activeIndex) && !hasError) {
      const firstLoaded = Array.from(loadedSet)[0]
      if (videoRefs.current[firstLoaded]) {
        videoRefs.current[firstLoaded]?.play().catch(() => {})
      }
    }
  }, [loadedSet, activeIndex, hasError])

  return (
    <div className="media-stage" aria-hidden="true">
      <div className="video-overlay" />
      <div className="media-stage__video" />
      <div className="media-stage__beam media-stage__beam-a" />
      <div className="media-stage__beam media-stage__beam-b" />
      <div className="media-stage__grain" />
      <div className="media-stage__glass" />

      {VIDEOS.map((src, index) => (
        <video
          key={src}
          ref={el => { videoRefs.current[index] = el }}
          className={`video-background ${
            loadedSet.has(index) && index === activeIndex ? "loaded" : ""
          } ${index === activeIndex ? "active" : ""}`}
          autoPlay
          loop
          muted
          playsInline
          preload="auto"
          onLoadedData={() => handleVideoLoaded(index)}
          onError={() => handleVideoError(index)}
          src={src}
          aria-hidden="true"
        />
      ))}

      <div className="video-progress-dots" role="presentation">
        {VIDEOS.map((_, index) => (
          <span
            key={index}
            className={`video-dot ${index === activeIndex ? "active" : ""}`}
            aria-hidden="true"
          />
        ))}
      </div>
    </div>
  )
}
