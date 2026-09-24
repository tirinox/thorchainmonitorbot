import {ref} from 'vue'

// A shared clock (unix seconds) ticking once per second, so "3 min ago" / "in 5 min" labels stay current
// between data reloads.
const now = ref(Date.now() / 1000)
let timer = null

export function useNow() {
    if (!timer) {
        timer = setInterval(() => (now.value = Date.now() / 1000), 1000)
    }
    return now
}
