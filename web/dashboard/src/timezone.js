import {computed, ref} from 'vue'

// Which timezone the dashboard shows absolute times in: the browser's own or UTC.
// (Schedules are always evaluated in the bot's scheduler timezone; the API reports it.)

const STORAGE_KEY = 'dashboard-display-tz'

export const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

function readStored() {
    try {
        return localStorage.getItem(STORAGE_KEY)
    } catch {
        return null
    }
}

export const displayMode = ref(readStored() === 'utc' ? 'utc' : 'local')

export const displayTz = computed(() => displayMode.value === 'utc' ? 'UTC' : browserTz)

export function toggleDisplayTz() {
    displayMode.value = displayMode.value === 'utc' ? 'local' : 'utc'
    try {
        localStorage.setItem(STORAGE_KEY, displayMode.value)
    } catch {
        // the choice just won't survive a reload
    }
}

/** "UTC", "GMT+3", "EST"… for a zone at a given moment (offsets change with DST). */
export function tzShortName(tz, ts = Date.now() / 1000) {
    try {
        const parts = new Intl.DateTimeFormat('en-US', {timeZone: tz, timeZoneName: 'short'})
            .formatToParts(new Date(ts * 1000))
        return parts.find(p => p.type === 'timeZoneName')?.value || tz
    } catch {
        return tz
    }
}

/** Same UTC offset right now? (then showing both zones is just noise) */
export function sameOffset(tzA, tzB, ts = Date.now() / 1000) {
    return tzShortName(tzA, ts) === tzShortName(tzB, ts)
}
