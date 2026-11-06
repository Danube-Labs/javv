import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

/** Puts `text` on the clipboard, or says with a toast that the browser blocked it: a page on plain
 *  http that is not localhost has no clipboard, and a browser can refuse the write. The caller
 *  shows "Copied" on true. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard) throw new DOMException('no clipboard', 'NotSupportedError')
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    logger.warn('clipboard_blocked')
    useToastStore().error("Couldn't copy: the browser blocked the clipboard. Select the text and copy it.")
    return false
  }
}
