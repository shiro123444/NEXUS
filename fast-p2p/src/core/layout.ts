import type { ColorInput, LayoutRect, LayoutNode } from "./types"

export type { LayoutRect, LayoutNode } from "./types"

export interface BoxStyle {
  width?: number | "100%"
  height?: number | "100%"
  position?: "absolute"
  top?: number
  left?: number
  backgroundColor?: ColorInput
  foregroundColor?: ColorInput
  flexDirection?: "row" | "column"
  flexGrow?: number
  flexShrink?: number
  flexBasis?: number
  gap?: number
  padding?: number
  paddingTop?: number
  paddingBottom?: number
  paddingLeft?: number
  paddingRight?: number
  margin?: number
  marginTop?: number
  marginBottom?: number
  marginLeft?: number
  marginRight?: number
  alignItems?: "flex-start" | "center" | "flex-end" | "stretch"
  justifyContent?: "flex-start" | "center" | "flex-end" | "space-between" | "space-around"
}

export class LayoutEngine {
  private static getPadding(node: LayoutNode): { top: number; right: number; bottom: number; left: number } {
    return {
      top: node.paddingTop ?? node.padding ?? 0,
      right: node.paddingRight ?? node.padding ?? 0,
      bottom: node.paddingBottom ?? node.padding ?? 0,
      left: node.paddingLeft ?? node.padding ?? 0,
    }
  }

  private static measureIntrinsic(node: LayoutNode): { width: number; height: number } {
    let width = node.rect.width
    let height = node.rect.height

    const flowChildren = node.children.filter((child) => child.position !== "absolute")

    if (flowChildren.length === 0) {
      return { width: Math.max(0, width), height: Math.max(0, height) }
    }

    const isRow = node.flexDirection === "row"
    const gap = node.gap ?? 0
    const { top, right, bottom, left } = this.getPadding(node)

    const childSizes = flowChildren.map((child) => this.measureIntrinsic(child))
    const totalGap = gap * Math.max(0, childSizes.length - 1)

    if (width <= 0) {
      if (isRow) {
        width = childSizes.reduce((sum, child) => sum + child.width, 0) + totalGap + left + right
      } else {
        width = childSizes.reduce((max, child) => Math.max(max, child.width), 0) + left + right
      }
    }

    if (height <= 0) {
      if (isRow) {
        height = childSizes.reduce((max, child) => Math.max(max, child.height), 0) + top + bottom
      } else {
        height = childSizes.reduce((sum, child) => sum + child.height, 0) + totalGap + top + bottom
      }
    }

    return { width: Math.max(0, width), height: Math.max(0, height) }
  }

  static calculate(node: LayoutNode, container: LayoutRect): void {
    // Only override dimensions that weren't explicitly set
    const hasExplicitWidth = node.rect.width > 0 && node.flexGrow === 0 && node.flexBasis === 0
    const hasExplicitHeight = node.rect.height > 0 && node.flexGrow === 0 && node.flexBasis === 0

    const ml = node.marginLeft ?? node.margin ?? 0
    const mr = node.marginRight ?? node.margin ?? 0
    const mt = node.marginTop ?? node.margin ?? 0
    const mb = node.marginBottom ?? node.margin ?? 0

    node.rect = {
      x: container.x + ml,
      y: container.y + mt,
      width: hasExplicitWidth ? node.rect.width : container.width - ml - mr,
      height: hasExplicitHeight ? node.rect.height : container.height - mt - mb,
    }

    const children = node.children
    if (children.length === 0) return

    // Compute content area (inside padding) for child layout
    const pt = node.paddingTop ?? node.padding ?? 0
    const pb = node.paddingBottom ?? node.padding ?? 0
    const pl = node.paddingLeft ?? node.padding ?? 0
    const pr = node.paddingRight ?? node.padding ?? 0

    const contentRect: LayoutRect = {
      x: node.rect.x + pl,
      y: node.rect.y + pt,
      width: node.rect.width - pl - pr,
      height: node.rect.height - pt - pb,
    }

    const isRow = node.flexDirection === "row"
    const mainAxis = isRow ? "width" : "height"
    const crossAxis = isRow ? "height" : "width"
    const gap = node.gap ?? 0
    const flowChildren = children.filter((child) => child.position !== "absolute")
    const absoluteChildren = children.filter((child) => child.position === "absolute")

    for (const child of flowChildren) {
      const measured = this.measureIntrinsic(child)

      if (isRow) {
        if (child.rect.width <= 0 && child.flexGrow === 0 && child.flexBasis === 0) {
          child.rect.width = measured.width
        }
        if (child.rect.height <= 0) {
          child.rect.height = measured.height
        }
      } else {
        if (child.rect.height <= 0 && child.flexGrow === 0 && child.flexBasis === 0) {
          child.rect.height = measured.height
        }
        if (child.rect.width <= 0) {
          child.rect.width = measured.width
        }
      }
    }

    let totalFlexGrow = 0
    let totalFlexShrink = 0
    const childMainSizes: number[] = []

    for (const child of flowChildren) {
      const flexBasis = child.flexBasis > 0 ? child.flexBasis : isRow ? child.rect.width : child.rect.height
      const flexGrow = child.flexGrow || 0
      const flexShrink = child.flexShrink ?? 1

      childMainSizes.push(flexBasis)

      if (flexBasis === 0 && flexGrow > 0) {
        totalFlexGrow += flexGrow
      }
      if (flexBasis === 0 && flexShrink > 0) {
        totalFlexShrink += flexShrink
      }
    }

    const totalGapSpace = gap * Math.max(0, flowChildren.length - 1)
    const contentSize = childMainSizes.reduce((a, b) => a + b, 0)
    const remainingSpace = contentRect[mainAxis] - contentSize - totalGapSpace

    let actualGap = gap
    let mainOffset = 0

    if (remainingSpace > 0 && totalFlexGrow > 0) {
      const flexGrowPerUnit = remainingSpace / totalFlexGrow
      for (const child of flowChildren) {
        if (child.flexGrow > 0 && child.flexBasis === 0) {
          const newSize = Math.floor(flexGrowPerUnit * child.flexGrow)
          if (isRow) {
            child.rect.width = newSize
          } else {
            child.rect.height = newSize
          }
        }
      }
    } else if (remainingSpace < 0 && totalFlexShrink > 0) {
      const shrinkPerUnit = remainingSpace / totalFlexShrink
      for (const child of flowChildren) {
        if (child.flexBasis === 0 && child.flexShrink > 0) {
          const shrink = Math.floor(shrinkPerUnit * child.flexShrink)
          if (isRow) {
            child.rect.width = Math.max(1, child.rect.width + shrink)
          } else {
            child.rect.height = Math.max(1, child.rect.height + shrink)
          }
        }
      }
    }

    const justify = node.justifyContent || "flex-start"
    const totalChildMainSize = flowChildren.reduce((sum, c) => sum + (isRow ? c.rect.width : c.rect.height), 0)
    const totalMainWithGap = totalChildMainSize + actualGap * Math.max(0, flowChildren.length - 1)

    if (justify === "center") {
      mainOffset = Math.floor((contentRect[mainAxis] - totalMainWithGap) / 2)
    } else if (justify === "flex-end") {
      mainOffset = contentRect[mainAxis] - totalMainWithGap
    } else if (justify === "space-between" && flowChildren.length > 1) {
      actualGap = (contentRect[mainAxis] - totalChildMainSize) / (flowChildren.length - 1)
    } else if (justify === "space-around" && flowChildren.length > 0) {
      actualGap = (contentRect[mainAxis] - totalChildMainSize) / (flowChildren.length + 1)
      mainOffset = actualGap
    }

    for (const child of flowChildren) {
      if (isRow) {
        child.rect.x = contentRect.x + mainOffset
        child.rect.y = contentRect.y

        if (node.alignItems === "center") {
          child.rect.y = contentRect.y + Math.floor((contentRect.height - child.rect.height) / 2)
        } else if (node.alignItems === "flex-end") {
          child.rect.y = contentRect.y + contentRect.height - child.rect.height
        } else if (node.alignItems === "stretch") {
          child.rect.height = contentRect.height
        }

        mainOffset += child.rect.width + actualGap
      } else {
        child.rect.x = contentRect.x
        child.rect.y = contentRect.y + mainOffset

        if (node.alignItems === "center") {
          child.rect.x = contentRect.x + Math.floor((contentRect.width - child.rect.width) / 2)
        } else if (node.alignItems === "flex-end") {
          child.rect.x = contentRect.x + contentRect.width - child.rect.width
        } else if (node.alignItems === "stretch") {
          child.rect.width = contentRect.width
        }

        mainOffset += child.rect.height + actualGap
      }

      this.calculate(child, child.rect)
    }

    for (const child of absoluteChildren) {
      const measured = this.measureIntrinsic(child)
      child.rect.x = contentRect.x + (child.left ?? 0)
      child.rect.y = contentRect.y + (child.top ?? 0)
      child.rect.width = child.rect.width > 0 ? child.rect.width : measured.width
      child.rect.height = child.rect.height > 0 ? child.rect.height : measured.height
      this.calculate(child, child.rect)
    }
  }

  static fromStyle(style: BoxStyle, children: LayoutNode[]): LayoutNode {
    const isRow = style.flexDirection === "row"
    const crossAxisSize = isRow ? style.height : style.width

    // "100%" means fill parent — use 0 so calculate() fills from container
    const w = typeof style.width === "number" ? style.width : 0
    const h = typeof style.height === "number" ? style.height : 0

    return {
      rect: { x: 0, y: 0, width: w, height: h },
      position: style.position === "absolute" ? "absolute" : "flow",
      top: style.top ?? 0,
      left: style.left ?? 0,
      flexGrow: style.flexGrow ?? 0,
      flexShrink: style.flexShrink ?? 1,
      flexBasis: style.flexBasis ?? 0,
      flexDirection: style.flexDirection ?? "column",
      alignItems: style.alignItems ?? (crossAxisSize !== undefined ? "flex-start" : "stretch"),
      justifyContent: style.justifyContent ?? "flex-start",
      gap: style.gap ?? 0,
      padding: style.padding ?? 0,
      paddingTop: style.paddingTop ?? 0,
      paddingBottom: style.paddingBottom ?? 0,
      paddingLeft: style.paddingLeft ?? 0,
      paddingRight: style.paddingRight ?? 0,
      margin: style.margin ?? 0,
      marginTop: style.marginTop ?? 0,
      marginBottom: style.marginBottom ?? 0,
      marginLeft: style.marginLeft ?? 0,
      marginRight: style.marginRight ?? 0,
      children,
    }
  }
}
