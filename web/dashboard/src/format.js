import {displayTz} from './timezone.js'

export const nowSec = () => Date.now() / 1000

export function durationHuman(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—'
    let s = Math.abs(Number(seconds))
    if (s < 1) return `${s.toFixed(2)} s`
    if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`
    const units = [['d', 86400], ['h', 3600], ['m', 60], ['s', 1]]
    const parts = []
    for (const [name, size] of units) {
        const n = Math.floor(s / size)
        if (n > 0) {
            parts.push(`${n}${name}`)
            s -= n * size
        }
        if (parts.length === 2) break
    }
    return parts.join(' ')
}

export function timeAgo(ts, now = nowSec()) {
    if (!ts) return 'never'
    return now - ts < 1 ? 'just now' : `${durationHuman(now - ts)} ago`
}

export function timeUntil(ts, now = nowSec()) {
    if (!ts) return '—'
    const diff = ts - now
    return diff >= 0 ? `in ${durationHuman(diff)}` : `overdue ${durationHuman(-diff)}`
}

/** Full date and time in the display timezone (or `tz`); `tzName` appends "GMT+3" / "UTC". */
export function formatDate(ts, {tz = null, tzName = false} = {}) {
    if (!ts) return '—'
    return new Date(ts * 1000).toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
        timeZone: tz || displayTz.value,
        ...(tzName ? {timeZoneName: 'short'} : {}),
    })
}

/** Compact "Thu, 25 Sep, 12:00" for run lists. */
export function formatRunTime(ts, {tz = null, tzName = false} = {}) {
    if (!ts) return '—'
    return new Date(ts * 1000).toLocaleString(undefined, {
        weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
        timeZone: tz || displayTz.value,
        ...(tzName ? {timeZoneName: 'short'} : {}),
    })
}

export function formatNumber(value, digits = 0) {
    if (value === null || value === undefined || Number.isNaN(value)) return '—'
    return Number(value).toLocaleString(undefined, {maximumFractionDigits: digits, minimumFractionDigits: digits})
}

export function formatPercent(part, total, digits = 1) {
    if (total === undefined) {
        // `part` is already a percentage
        return part === null || part === undefined ? '—' : `${Number(part).toFixed(digits)}%`
    }
    if (!total) return '—'
    return `${(100 * part / total).toFixed(digits)}%`
}

export function formatUsd(value) {
    if (value === null || value === undefined) return '—'
    return Number(value).toLocaleString(undefined, {style: 'currency', currency: 'USD', maximumFractionDigits: 0})
}

export function shortJson(value, max = 160) {
    const text = JSON.stringify(value)
    return text.length > max ? `${text.slice(0, max - 1)}…` : text
}
