import {onBeforeUnmount, onMounted, ref, shallowRef} from 'vue'
import {onEvent} from '../events.js'

/**
 * Loads data with `fetcher` and keeps it fresh.
 *
 * - `refreshOn`: event types (see events.js) that trigger a reload; bursts are coalesced into one reload
 *   per `eventDelay` ms. A "resync" (after an SSE reconnect) always reloads.
 * - `eventFilter(event)`: optional, return false to ignore an event.
 * - `interval`: plain polling period in ms. With `refreshOn` it is only a safety net, so keep it long.
 *
 * Requests never overlap; a failed request keeps the last good data and exposes `error`.
 * `refresh()` during a request schedules one more request right after it (e.g. filters changed).
 */
export function usePolling(fetcher, {
    interval = 2000,
    immediate = true,
    refreshOn = null,
    eventFilter = null,
    eventDelay = 300,
} = {}) {
    const data = shallowRef(null)
    const error = ref(null)
    const loading = ref(false)
    const updatedAt = ref(null)

    let timer = null
    let eventTimer = null
    let stopped = false
    let inFlight = null
    let again = false

    async function refresh() {
        if (inFlight) {
            again = true
            return inFlight
        }
        loading.value = true
        inFlight = (async () => {
            try {
                do {
                    again = false
                    const result = await fetcher()
                    if (!again) {
                        data.value = result
                        error.value = null
                        updatedAt.value = new Date()
                    }
                } while (again && !stopped)
            } catch (e) {
                error.value = e
            } finally {
                loading.value = false
                inFlight = null
            }
        })()
        return inFlight
    }

    function schedule() {
        clearTimeout(timer)
        if (stopped || !interval) return
        timer = setTimeout(async () => {
            if (!document.hidden) await refresh()
            schedule()
        }, interval)
    }

    // throttle with a trailing call: the first event arms a timer, later ones ride along
    function refreshSoon() {
        if (eventTimer || stopped) return
        eventTimer = setTimeout(() => {
            eventTimer = null
            if (!document.hidden) refresh()
        }, eventDelay)
    }

    if (refreshOn) {
        onEvent(refreshOn, (event) => {
            if (!eventFilter || eventFilter(event)) refreshSoon()
        })
        onEvent('resync', refreshSoon)
    }

    function onVisibility() {
        if (!document.hidden) refresh()
    }

    onMounted(() => {
        if (immediate) refresh()
        schedule()
        document.addEventListener('visibilitychange', onVisibility)
    })

    onBeforeUnmount(() => {
        stopped = true
        clearTimeout(timer)
        clearTimeout(eventTimer)
        document.removeEventListener('visibilitychange', onVisibility)
    })

    return {data, error, loading, updatedAt, refresh}
}
