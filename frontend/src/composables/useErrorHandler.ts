import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getApiErrorMessage } from '../utils/http'

export function useErrorHandler(options?: { showMessages?: boolean }) {
  const errorMessage = ref('')
  const { showMessages = true } = options ?? {}

  function handleError(error: unknown, fallbackMessage = '操作失败'): string {
    const message = getApiErrorMessage(error, fallbackMessage)
    errorMessage.value = message

    if (showMessages) {
      ElMessage.error(message)
    }

    return message
  }

  function clearError(): void {
    errorMessage.value = ''
  }

  return {
    errorMessage,
    handleError,
    clearError,
  }
}
