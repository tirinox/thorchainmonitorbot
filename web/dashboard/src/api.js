// All requests go to <base>/api/... so the app works under /dashboard/ behind nginx and in `vite dev`.
const API_BASE = `${import.meta.env.BASE_URL}api`

export class ApiError extends Error {
    constructor(message, status, detail) {
        super(message)
        this.status = status
        this.detail = detail
    }
}

function describeDetail(detail) {
    if (!detail) return ''
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
        // FastAPI / pydantic validation errors
        return detail.map(e => {
            const loc = (e.loc || []).filter(p => p !== 'body').join('.')
            return loc ? `${loc}: ${e.msg}` : e.msg
        }).join('; ')
    }
    return JSON.stringify(detail)
}

async function request(method, path, {body, query} = {}) {
    let url = `${API_BASE}${path}`
    if (query) {
        const params = new URLSearchParams()
        for (const [k, v] of Object.entries(query)) {
            if (v !== undefined && v !== null && v !== '') params.set(k, v)
        }
        const qs = params.toString()
        if (qs) url += `?${qs}`
    }

    const headers = {Accept: 'application/json'}
    if (method !== 'GET') {
        headers['X-Dashboard-Request'] = '1'  // required by the server's CSRF guard
    }
    if (body !== undefined) {
        headers['Content-Type'] = 'application/json'
    }

    const response = await fetch(url, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
    })

    let payload = null
    const text = await response.text()
    if (text) {
        try {
            payload = JSON.parse(text)
        } catch {
            payload = text
        }
    }

    if (!response.ok) {
        const detail = payload && typeof payload === 'object' ? payload.detail : payload
        const message = describeDetail(detail) || `${response.status} ${response.statusText}`
        throw new ApiError(message, response.status, detail)
    }
    return payload
}

const enc = encodeURIComponent

export const api = {
    overview: (section) => request('GET', `/overview/${section}`),

    jobs: () => request('GET', '/jobs'),
    createJob: (job) => request('POST', '/jobs', {body: job}),
    updateJob: (id, job) => request('PUT', `/jobs/${enc(id)}`, {body: job}),
    deleteJob: (id) => request('DELETE', `/jobs/${enc(id)}`),
    setJobEnabled: (id, enabled) => request('POST', `/jobs/${enc(id)}/enabled`, {body: {enabled}}),
    // both return a run record at once (202); progress arrives as `run` events
    runJob: (id, timeout) => request('POST', `/jobs/${enc(id)}/run`, {body: timeout ? {timeout} : {}}),
    runFunction: (func, args, timeout) => request('POST', '/run-now', {body: {func, args, timeout}}),
    runs: () => request('GET', '/runs'),
    reloadScheduler: () => request('POST', '/scheduler/reload'),

    logs: (filters) => request('GET', '/logs', {query: filters}),

    flags: () => request('GET', '/flags'),
    setFlag: (path, value) => request('PUT', '/flags', {body: {path, value}}),
    deleteFlag: (path) => request('DELETE', '/flags', {query: {path}}),
}
