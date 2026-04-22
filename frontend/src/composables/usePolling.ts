import { onBeforeUnmount, ref } from 'vue'

export function usePolling(intervalMs = 30000) {
  const isPolling = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  function startPolling(callback: () => void): void {
    stopPolling()
    isPolling.value = true
    callback()
    timer = setInterval(callback, intervalMs)
  }

  function stopPolling(): void {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    isPolling.value = false
  }

  onBeforeUnmount(() => {
    stopPolling()
  })

  return {
    isPolling,
    startPolling,
    stopPolling,
  }
}
