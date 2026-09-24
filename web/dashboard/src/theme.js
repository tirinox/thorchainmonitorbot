import {ref} from 'vue'

const STORAGE_KEY = 'dashboard-theme'

export const isDark = ref(false)

function readStored() {
    try {
        return localStorage.getItem(STORAGE_KEY)
    } catch {
        return null
    }
}

function apply() {
    document.documentElement.classList.toggle('app-dark', isDark.value)
}

export function initTheme() {
    const stored = readStored()
    isDark.value = stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
    apply()
}

export function toggleTheme() {
    isDark.value = !isDark.value
    apply()
    try {
        localStorage.setItem(STORAGE_KEY, isDark.value ? 'dark' : 'light')
    } catch {
        // storage may be unavailable; the theme still switches for this session
    }
}
