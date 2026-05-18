import { useEffect, useRef, useState } from "react"

type ParallaxLayer = {
  speed: number
  direction: "both" | "horizontal" | "vertical"
}

export function useScrollParallax(layers: ParallaxLayer[] = []) {
  const containerRef = useRef<HTMLElement | null>(null)
  const [scrollProgress, setScrollProgress] = useState(0)
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 })
  const rafRef = useRef<number | null>(null)
  const smoothMouseRef = useRef({ x: 0, y: 0 })

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const handleScroll = () => {
      const rect = container.getBoundingClientRect()
      const viewportHeight = window.innerHeight
      const elementTop = -rect.top
      const elementHeight = rect.height
      
      const progress = Math.max(0, Math.min(1, elementTop / (elementHeight - viewportHeight)))
      setScrollProgress(progress)
    }

    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({
        x: (e.clientX / window.innerWidth - 0.5) * 2,
        y: (e.clientY / window.innerHeight - 0.5) * 2
      })
    }

    const animate = () => {
      smoothMouseRef.current.x += (mousePosition.x - smoothMouseRef.current.x) * 0.05
      smoothMouseRef.current.y += (mousePosition.y - smoothMouseRef.current.y) * 0.05
      
      rafRef.current = requestAnimationFrame(animate)
    }

    window.addEventListener("scroll", handleScroll, { passive: true })
    window.addEventListener("mousemove", handleMouseMove, { passive: true })
    rafRef.current = requestAnimationFrame(animate)

    handleScroll()

    return () => {
      window.removeEventListener("scroll", handleScroll)
      window.removeEventListener("mousemove", handleMouseMove)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [mousePosition])

  const getTransform = (layer: ParallaxLayer, baseOffset: number = 0) => {
    const { speed, direction } = layer
    
    let translateX = 0
    let translateY = 0

    if (direction === "both" || direction === "horizontal") {
      translateX = smoothMouseRef.current.x * speed * 30 + scrollProgress * speed * 100
    }
    
    if (direction === "both" || direction === "vertical") {
      translateY = smoothMouseRef.current.y * speed * 20 + scrollProgress * speed * 80
    }

    return `translate(${translateX}px, ${translateY}px)`
  }

  return {
    containerRef,
    scrollProgress,
    mousePosition,
    getTransform,
    smoothMouse: smoothMouseRef.current
  }
}
