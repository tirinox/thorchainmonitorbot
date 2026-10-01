import {getCurrentScope, onScopeDispose, ref} from 'vue'

// One EventSource for the whole app. The server sends every event as a plain "message" whose JSON has a `type`.
// Types: log, scanner, fetchers, flags, run (see app/lib/events.py) plus the local "resync" emitted after a
// reconnect, when anything could have been missed and views should reload.

const URL = `${import.meta.env.BASE_URL}api/events`

// 'connecting' | 'live' | 'reconnecting'
export const liveStatus = ref('connecting')

const handlers = new Map()  // type -> Set<fn>
let source = null
let wasConnected = false

const RETRY_MIN_MS = 2000
const RETRY_MAX_MS = 30000
let retryMs = RETRY_MIN_MS
let retryTimer = null

function emit(type, event) {
    for (const fn of handlers.get(type) || []) {
        try {
            fn(event)
        } catch (e) {
            console.error(`Event handler for "${type}" failed`, e)
        }
    }
}

function open() {
    const es = source = new EventSource(URL)

    es.onmessage = (msg) => {
        let event
        try {
            event = JSON.parse(msg.data)
        } catch {
            return
        }
        if (event.type === 'hello') {
            retryMs = RETRY_MIN_MS
            liveStatus.value = 'live'
            if (wasConnected) emit('resync', event)
            wasConnected = true
            return
        }
        emit(event.type, event)
    }

    es.onerror = () => {
        if (es !== source) return
        liveStatus.value = wasConnected ? 'reconnecting' : 'connecting'
        // A dropped connection is reopened by the browser itself (the server sets `retry`), the state is CONNECTING
        // then. But an answer that is not a 200 event stream (502 while the dashboard restarts, 401...) closes
        // the EventSource for good, so it has to be opened anew.
        if (es.readyState === EventSource.CLOSED) reopenLater()
    }
}

function reopenLater() {
    source.close()
    source = null
    retryTimer = setTimeout(() => {
        retryTimer = null
        open()
    }, retryMs)
    retryMs = Math.min(retryMs * 2, RETRY_MAX_MS)
}

export function connectEvents() {
    if (source || retryTimer) return
    open()
}

/**
 * Subscribes `fn` to one or more event types; unsubscribes automatically with the calling component/scope.
 * Returns an unsubscribe function for use outside components.
 */
export function onEvent(types, fn) {
    const list = Array.isArray(types) ? types : [types]
    for (const t of list) {
        if (!handlers.has(t)) handlers.set(t, new Set())
        handlers.get(t).add(fn)
    }
    const off = () => list.forEach(t => handlers.get(t)?.delete(fn))
    if (getCurrentScope()) onScopeDispose(off)
    return off
}
