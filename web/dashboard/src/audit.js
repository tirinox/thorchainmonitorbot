// How activity log (audit) entries are shown. Actions come from app/dashboard/audit.py (AuditAction).

const ACTIONS = {
    'job.create': {label: 'Created job', icon: 'pi pi-plus', severity: 'success'},
    'job.update': {label: 'Edited job', icon: 'pi pi-pencil', severity: 'info'},
    'job.delete': {label: 'Deleted job', icon: 'pi pi-trash', severity: 'danger'},
    'job.enable': {label: 'Enabled job', icon: 'pi pi-check', severity: 'success'},
    'job.disable': {label: 'Disabled job', icon: 'pi pi-ban', severity: 'warn'},
    'job.run': {label: 'Ran job', icon: 'pi pi-play', severity: 'secondary'},
    'function.run': {label: 'Ran function', icon: 'pi pi-play', severity: 'secondary'},
    'scheduler.apply': {label: 'Applied config', icon: 'pi pi-check-circle', severity: 'info'},
    'flag.set': {label: 'Changed flag', icon: 'pi pi-flag', severity: 'info'},
    'flag.delete': {label: 'Deleted flag', icon: 'pi pi-trash', severity: 'danger'},
}

export function actionInfo(action) {
    return ACTIONS[action] || {label: action, icon: 'pi pi-circle', severity: 'secondary'}
}

export function formatValue(value) {
    if (value === null || value === undefined) return '∅'
    if (typeof value === 'object') return JSON.stringify(value)
    return String(value)
}

// one short line for lists (the Activity page shows the full details)
export function auditSummary(entry) {
    const d = entry.details || {}
    switch (entry.action) {
        case 'flag.set':
            return `${formatValue(d.old)} → ${formatValue(d.new)}`
        case 'job.update': {
            const keys = Object.keys(d.changes || {})
            return keys.length ? `changed ${keys.join(', ')}` : 'saved without changes'
        }
        case 'job.create':
            return [d.func, d.schedule].filter(Boolean).join(' · ')
        case 'scheduler.apply':
            return d.ok ? 'ok' : `failed: ${formatValue(d.result)}`
        default:
            return d.func || ''
    }
}
