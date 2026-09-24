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

function emit(type, event) {
    for (const fn of handlers.get(type) || []) {
        try {
            fn(event)
        } catch (e) {
            console.error(`Event handler for "${type}" failed`, e)
        }
    }
}

export function connectEvents() {
    if (source) return
    source = new EventSource(URL)

    source.onmessage = (msg) => {
        let event
        try {
            event = JSON.parse(msg.data)
        } catch {
            return
        }
        if (event.type === 'hello') {
            liveStatus.value = 'live'
            if (wasConnected) emit('resync', event)
            wasConnected = true
            return
        }
        emit(event.type, event)
    }

    // EventSource reconnects by itself (the server sets `retry`)
    source.onerror = () => {
        liveStatus.value = wasConnected ? 'reconnecting' : 'connecting'
    }
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
