import { onBeforeUnmount, ref } from 'vue'

export type GraphCoordMode = 'pixel' | 'percent'

export interface GraphNodeInteractionOptions {
  coordMode: GraphCoordMode
  getBoardElement: () => HTMLElement | null
  getCanvasSize: () => { width: number; height: number }
  getNodeSize?: (id: string) => { w: number; h: number }
  getScale?: () => number
  onNodeMove: (id: string, x: number, y: number) => void
  onDragEnd?: () => void
}

const DRAG_THRESHOLD = 5

export function useGraphNodeInteraction(options: GraphNodeInteractionOptions) {
  const focusedNodeId = ref<string | null>(null)
  const draggingNodeId = ref<string | null>(null)
  const dragMoved = ref(false)
  const dragOrigin = ref({ mouseX: 0, mouseY: 0, x: 0, y: 0 })

  function clampPosition(id: string, x: number, y: number) {
    const canvas = options.getCanvasSize()
    const size = options.getNodeSize?.(id) ?? { w: 0, h: 0 }

    if (options.coordMode === 'percent') {
      return {
        x: Math.min(100 - size.w, Math.max(0, x)),
        y: Math.min(100 - size.h, Math.max(0, y)),
      }
    }

    return {
      x: Math.min(canvas.width - size.w, Math.max(0, x)),
      y: Math.min(canvas.height - size.h, Math.max(0, y)),
    }
  }

  function handleMouseMove(event: MouseEvent) {
    const nodeId = draggingNodeId.value
    if (!nodeId) {
      return
    }

    const dx = event.clientX - dragOrigin.value.mouseX
    const dy = event.clientY - dragOrigin.value.mouseY
    if (Math.hypot(dx, dy) > DRAG_THRESHOLD) {
      dragMoved.value = true
    }

    const board = options.getBoardElement()
    if (!board) {
      return
    }

    const scale = options.getScale?.() ?? 1

    if (options.coordMode === 'percent') {
      const deltaX = (dx / board.clientWidth) * 100
      const deltaY = (dy / board.clientHeight) * 100
      const next = clampPosition(nodeId, dragOrigin.value.x + deltaX, dragOrigin.value.y + deltaY)
      options.onNodeMove(nodeId, next.x, next.y)
      return
    }

    const deltaX = dx / scale
    const deltaY = dy / scale
    const next = clampPosition(nodeId, dragOrigin.value.x + deltaX, dragOrigin.value.y + deltaY)
    options.onNodeMove(nodeId, next.x, next.y)
  }

  function stopDrag() {
    const didMove = dragMoved.value
    draggingNodeId.value = null
    window.removeEventListener('mousemove', handleMouseMove)
    window.removeEventListener('mouseup', stopDrag)
    if (didMove) {
      options.onDragEnd?.()
    }
  }

  function startNodeDrag(nodeId: string, event: MouseEvent, nodeX: number, nodeY: number) {
    if (event.button !== 0) {
      return
    }
    event.preventDefault()
    draggingNodeId.value = nodeId
    dragMoved.value = false
    dragOrigin.value = {
      mouseX: event.clientX,
      mouseY: event.clientY,
      x: nodeX,
      y: nodeY,
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', stopDrag)
  }

  function handleNodeClick(nodeId: string) {
    if (dragMoved.value) {
      dragMoved.value = false
      return
    }
    focusedNodeId.value = focusedNodeId.value === nodeId ? null : nodeId
  }

  function nodeClasses(nodeId: string) {
    return {
      dragging: draggingNodeId.value === nodeId,
      focused: focusedNodeId.value === nodeId,
    }
  }

  function clearFocus() {
    focusedNodeId.value = null
  }

  onBeforeUnmount(stopDrag)

  return {
    focusedNodeId,
    draggingNodeId,
    startNodeDrag,
    handleNodeClick,
    nodeClasses,
    clearFocus,
  }
}
