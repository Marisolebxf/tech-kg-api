import { computed, ref, watch, type CSSProperties } from 'vue'

export function useAdaptiveGraphViewport(defaultWidth = 720, defaultHeight = 480) {
  const viewportRef = ref<HTMLElement | null>(null)
  const canvasWidth = ref(defaultWidth)
  const canvasHeight = ref(defaultHeight)
  const scale = ref(1)

  function updateScale() {
    const el = viewportRef.value
    if (!el || canvasWidth.value <= 0 || canvasHeight.value <= 0) {
      return
    }
    const margin = 16
    const availW = Math.max(0, el.clientWidth - margin * 2)
    const availH = Math.max(0, el.clientHeight - margin * 2)
    const sx = availW / canvasWidth.value
    const sy = availH / canvasHeight.value
    scale.value = Math.min(1, sx, sy) * 0.94
  }

  function setCanvasSize(width: number, height: number) {
    canvasWidth.value = width
    canvasHeight.value = height
    updateScale()
  }

  const scaleWrapStyle = computed<CSSProperties>(() => {
    const s = scale.value
    return {
      width: `${canvasWidth.value * s}px`,
      height: `${canvasHeight.value * s}px`,
      flexShrink: 0,
    }
  })

  const boardStyle = computed<CSSProperties>(() => {
    const s = scale.value
    return {
      width: `${canvasWidth.value}px`,
      height: `${canvasHeight.value}px`,
      transform: s < 1 ? `scale(${s})` : undefined,
      transformOrigin: 'top left',
    }
  })

  watch(
    viewportRef,
    (el, _, onCleanup) => {
      if (!el) {
        return
      }
      updateScale()
      if (typeof ResizeObserver === 'undefined') {
        return
      }
      const observer = new ResizeObserver(() => updateScale())
      observer.observe(el)
      onCleanup(() => observer.disconnect())
    },
    { flush: 'post' },
  )

  return {
    viewportRef,
    canvasWidth,
    canvasHeight,
    scale,
    scaleWrapStyle,
    boardStyle,
    setCanvasSize,
    updateScale,
  }
}
