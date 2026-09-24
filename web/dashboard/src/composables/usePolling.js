import {onBeforeUnmount, onMounted, ref, shallowRef} from 'vue'

/**
 * Calls `fetcher` now and then every `interval` ms while the page is visible.
 * Requests never overlap; a failed request keeps the last good data and exposes `error`.
 * `refresh()` during a request schedules one more request right after it (e.g. filters changed).
 */
export function usePolling(fetcher, {interval = 2000, immediate = true} = {}) {
    const data = shallowRef(null)
    const error = ref(null)
    const loading = ref(false)
    const updatedAt = ref(null)

    let timer = null
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
        document.removeEventListener('visibilitychange', onVisibility)
    })

    return {data, error, loading, updatedAt, refresh}
}
