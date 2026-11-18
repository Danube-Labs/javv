/**
 * The cluster retirement window editor (issue 765): load, validate and save
 * `GET/PUT /api/v1/settings/retirement` the way the staleness timers do: an existing per-cluster
 * override is what gets edited, else the fleet default (also when no cluster is selected).
 * "Never" is a window of null. The scanner-down timer it is checked against is the one the
 * backend checks: the cluster's own for an override, the fleet's for the fleet default.
 */
import { computed, ref, watch, type Ref } from 'vue'

import { client } from '@/api/client'
import {
  getRetirementApiV1SettingsRetirementGet,
  putRetirementApiV1SettingsRetirementPut,
} from '@/api/generated'
import { detailOr } from '@/api/problem'
import { logger } from '@/lib/logger'

import { parseWindow } from './slaForm'

export interface RetirementWindow {
  retire_after_days: number | null
  warn_days: number
}

export type RetireMode = 'after' | 'never'

export interface WindowProblem {
  field: 'after' | 'warn'
  message: string
}

/** What stops the draft from being saved, and which input it concerns, or null. A scanner-down
 * timer not known yet (null) is left to the backend, which refuses the same thing with a 422. */
export function windowProblem(
  mode: RetireMode,
  after: number | null,
  warn: number | null,
  scannerDownDays: number | null,
): WindowProblem | null {
  if (warn === null) return { field: 'warn', message: 'The warning needs a number of days more than 0.' }
  if (mode === 'never') return null
  if (after === null) {
    return { field: 'after', message: 'The retirement window needs a number of days more than 0.' }
  }
  if (scannerDownDays !== null && after <= scannerDownDays) {
    return {
      field: 'after',
      message: `The retirement window must be longer than the scanner-down timer (${scannerDownDays} days).`,
    }
  }
  if (warn >= after) return { field: 'warn', message: 'The warning must be shorter than the retirement window.' }
  return null
}

const sentence = (text: string) => `${text.charAt(0).toUpperCase()}${text.slice(1)}.`

export function useRetirementWindow(clusterId: Ref<string | null>, scannerDownDays: Ref<number | null>) {
  const saved = ref<RetirementWindow | null>(null)
  const override = ref(false)
  const mode = ref<RetireMode>('after')
  const draftAfter = ref('')
  const draftWarn = ref('')
  const loading = ref(true)
  const failed = ref(false)
  const busy = ref(false)

  function reset(w: RetirementWindow) {
    mode.value = w.retire_after_days === null ? 'never' : 'after'
    draftAfter.value = w.retire_after_days === null ? '' : String(w.retire_after_days)
    draftWarn.value = String(w.warn_days)
  }

  // a read for a cluster no longer selected must not land: Save would write it to the wrong doc
  let latest = 0
  watch(
    clusterId,
    async (id) => {
      const mine = ++latest
      loading.value = true
      const { data, response } = await getRetirementApiV1SettingsRetirementGet({
        client,
        query: id ? { cluster_id: id } : {},
      })
      if (mine !== latest) return
      loading.value = false
      failed.value = !response?.ok || !data
      if (failed.value) {
        logger.warn('retirement_window_load_failed', { status: response?.status })
        return
      }
      const body = data as { retirement: RetirementWindow; per_cluster_override: boolean }
      saved.value = body.retirement
      override.value = body.per_cluster_override
      reset(body.retirement)
    },
    { immediate: true },
  )

  const after = computed(() => parseWindow(draftAfter.value))
  const warn = computed(() => parseWindow(draftWarn.value))
  const problem = computed(() => windowProblem(mode.value, after.value, warn.value, scannerDownDays.value))
  const draft = computed<RetirementWindow | null>(() =>
    problem.value !== null || warn.value === null
      ? null
      : { retire_after_days: mode.value === 'never' ? null : after.value, warn_days: warn.value },
  )
  const dirty = computed(
    () =>
      saved.value !== null &&
      (mode.value !== (saved.value.retire_after_days === null ? 'never' : 'after') ||
        (mode.value === 'after' && after.value !== saved.value.retire_after_days) ||
        warn.value !== saved.value.warn_days),
  )

  /** null on success, else the message to show. */
  async function save(): Promise<string | null> {
    const body = draft.value
    if (body === null) return problem.value?.message ?? 'The warning needs a number of days more than 0.'
    const forCluster = clusterId.value
    busy.value = true
    const { response, error } = await putRetirementApiV1SettingsRetirementPut({
      client,
      body: { ...body, ...(override.value && clusterId.value ? { cluster_id: clusterId.value } : {}) },
    })
    busy.value = false
    if (!response?.ok) {
      logger.warn('retirement_window_save_failed', { status: response?.status })
      if (response?.status === 403) return 'Your role cannot change the settings. It needs the permission can_manage_settings.'
      const refused = response?.status === 422 ? detailOr(error, '') : ''
      return refused
        ? `${sentence(refused)} The sweep keeps the current window.`
        : 'JAVV did not save the retirement window. The sweep keeps the current window.'
    }
    // the form moved on to another cluster meanwhile: its saved values are that cluster's
    if (clusterId.value === forCluster) saved.value = body
    return null
  }

  function discard() {
    if (saved.value !== null) reset(saved.value)
  }

  return { mode, draftAfter, draftWarn, after, warn, problem, dirty, override, loading, failed, busy, save, discard }
}
