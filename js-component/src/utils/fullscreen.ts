/**
 * Full screen for every view.
 *
 * Each view lives in a frame of its own, so the frame's document is the view:
 * putting it in full screen shows that view alone, whatever kind it is. App.vue
 * gives the view the screen's height while it is shown so; the plot toolbar
 * offers the switch on every plot, and the other views put FullscreenButton in
 * their own toolbars.
 */
import { ref } from 'vue'
import { plotly } from '@/plotly/current'

/** The view fills the screen. */
export const fullscreen = ref(false)

/** Height of the window, kept while in full screen (the views size to it). */
export const screenHeight = ref(typeof window === 'undefined' ? 0 : window.innerHeight)

let listening = false

function listen(): void {
  if (listening || typeof document === 'undefined') return
  listening = true
  document.addEventListener('fullscreenchange', () => {
    fullscreen.value = !!document.fullscreenElement
    screenHeight.value = window.innerHeight
  })
  window.addEventListener('resize', () => {
    screenHeight.value = window.innerHeight
  })
}

/** Whether this frame may go full screen (the page must allow it). */
export function fullscreenAvailable(): boolean {
  return typeof document !== 'undefined' && document.fullscreenEnabled !== false
}

export function toggleFullscreen(): void {
  listen()
  if (document.fullscreenElement) {
    void document.exitFullscreen()
  } else {
    void document.documentElement.requestFullscreen?.()
  }
}

/**
 * Grow (or shrink) every Plotly figure of this view by `delta` pixels and fit
 * it to its container's width: a view draws at its new height by itself only
 * on its next update. Views without Plotly have nothing to resize.
 */
export function resizePlots(delta: number): void {
  let Plotly: ReturnType<typeof plotly>
  try {
    Plotly = plotly()
  } catch {
    return
  }
  document.querySelectorAll<HTMLElement>('.js-plotly-plot').forEach((element) => {
    // Plots of another Plotly bundle size themselves from their height argument
    if (element.closest('[data-own-size]')) return
    const height = (element as unknown as { _fullLayout?: { height?: number } })._fullLayout?.height
    if (!height) return
    const width = element.parentElement?.clientWidth
    void Plotly.relayout(element, { height: Math.max(100, height + delta), ...(width ? { width } : {}) })
  })
}

export const FULLSCREEN_ICON = 'M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z'
export const EXIT_FULLSCREEN_ICON = 'M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z'

listen()
