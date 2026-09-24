import {computed, reactive} from 'vue'
import {api} from './api.js'
import {onEvent} from './events.js'

// Manual "run now" requests. The API answers at once with a run record; its progress arrives as `run` events.

export const runs = reactive({})  // run_id -> run

export const activeRuns = computed(() => Object.values(runs).filter(r => r.status === 'running'))

export const isFinished = (run) => !!run && run.status !== 'running'

export function activeRunForJob(jobId) {
    return activeRuns.value.find(r => r.job_id === jobId) || null
}

export function runLabel(run) {
    return run.job_id || run.func || run.run_id
}

let onRunFinished = null

/**
 * Merges a run record from the API or an event. Calls the finish handler once per run, unless the run
 * was already over when we first heard of it (history loaded on page open).
 */
function apply(run, {fromHistory = false} = {}) {
    const known = runs[run.run_id]
    // events may arrive out of order with the HTTP answer; never go back from a finished state
    if (isFinished(known) && !isFinished(run)) return
    const wasActive = !!known && !isFinished(known)
    runs[run.run_id] = {...known, ...run}

    const current = runs[run.run_id]
    if (isFinished(current) && !current.notified) {
        current.notified = true
        if (!fromHistory || wasActive) onRunFinished?.(current)
    }
}

export async function loadRuns() {
    try {
        for (const run of await api.runs()) apply(run, {fromHistory: true})
    } catch {
        // the list is only a convenience; live events still work
    }
}

export async function startJobRun(jobId, mode = 'normal') {
    const run = await api.runJob(jobId, mode)
    apply(run)
    return run
}

export async function startFunctionRun(func, args, timeout, mode = 'normal') {
    const run = await api.runFunction(func, args, timeout, mode)
    apply(run)
    return run
}

/** App-level wiring, call once from App.vue: `onFinished(run)` fires when a run ends. */
export function trackRuns(onFinished) {
    onRunFinished = onFinished
    onEvent('run', ({run}) => run && apply(run))
    onEvent('resync', loadRuns)  // catches runs that ended while the stream was down
    loadRuns()
}
