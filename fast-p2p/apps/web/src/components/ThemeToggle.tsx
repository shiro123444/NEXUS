type ThemeToggleProps = {
  theme: "light" | "dark"
  onToggle: () => void
}

export function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  return (
    <button
      className="theme-toggle"
      onClick={onToggle}
      aria-label={`切换到${theme === "light" ? "深色" : "浅色"}模式`}
      title={`切换到${theme === "light" ? "深色" : "浅色"}模式`}
    >
      <span className="theme-icon" aria-hidden="true">
        {theme === "light" ? "🌙" : "☀️"}
      </span>
    </button>
  )
}
