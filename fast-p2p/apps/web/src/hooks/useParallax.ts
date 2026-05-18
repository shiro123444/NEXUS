import { useEffect, useRef } from "react"

type ParallaxConfig = {
  strength?: number
  maxOffset?: number
}

export function useParallax(config: ParallaxConfig = {}) {
  const { strength = 50, maxOffset = 100 } = config
  const elementRef = useRef<HTMLElement | null>(null)
  const mouseRef = useRef({ x: 0, y: 0 })
  const scrollRef = useRef({ x: 0, y: 0 })
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    const element = elementRef.current
    if (!element) return

    const handleMouseMove = (e: MouseEvent) => {
      const rect = element.getBoundingClientRect()
      const centerX = rect.left + rect.width / 2
      const centerY = rect.top + rect.height / 2
      
      mouseRef.current = {
        x: (e.clientX - centerX) / (rect.width / 2),
        y: (e.clientY - centerY) / (rect.height / 2)
      }
    }

    const handleScroll = () => {
      scrollRef.current = {
        x: window.scrollX,
        y: window.scrollY
      }
    }

    const animate = () => {
      const offsetX = mouseRef.current.x * strength
      const offsetY = mouseRef.current.y * strength
      
      element.style.setProperty("--parallax-x", `${Math.max(-maxOffset, Math.min(maxOffset, offsetX))}px`)
      element.style.setProperty("--parallax-y", `${Math.max(-maxOffset, Math.min(maxOffset, offsetY))}px`)
      
      rafRef.current = requestAnimationFrame(animate)
    }

    window.addEventListener("mousemove", handleMouseMove)
    window.addEventListener("scroll", handleScroll, { passive: true })
    rafRef.current = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener("mousemove", handleMouseMove)
      window.removeEventListener("scroll", handleScroll)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [strength, maxOffset])

  return elementRef
}
