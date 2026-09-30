// A colour and an emoji per scheduled-job function (PublicAlertJobExecutor.AVAILABLE_TYPES in the bot), so the
// same kind of alert looks the same everywhere: the jobs table, the calendar, pickers, previews.

const JOB_TYPES = {
    tcy_summary: {emoji: '🪙', color: '#f59e0b', title: 'TCY summary'},
    secured_asset_summary: {emoji: '🔐', color: '#14b8a6', title: 'Secured assets'},
    pol_summary_adr024: {emoji: '🏦', color: '#6366f1', title: 'POL (ADR-024)'},
    runepool_summary: {emoji: '🏊', color: '#0ea5e9', title: 'RUNEPool'},
    key_metrics: {emoji: '📊', color: '#10b981', title: 'Key metrics'},
    top_pools: {emoji: '🏆', color: '#eab308', title: 'Top pools'},
    supply_chart: {emoji: '🥧', color: '#f97316', title: 'Supply chart'},
    rune_burn_chart: {emoji: '🔥', color: '#ef4444', title: 'RUNE burn'},
    trade_account_summary: {emoji: '💼', color: '#8b5cf6', title: 'Trade accounts'},
    price_alert: {emoji: '💹', color: '#22c55e', title: 'Price'},
    net_stats_summary: {emoji: '🌐', color: '#3b82f6', title: 'Network stats'},
    app_layer_stats: {emoji: '🧩', color: '#d946ef', title: 'App layer'},
    limit_swap_stats: {emoji: '🎯', color: '#f43f5e', title: 'Limit swaps'},
    rapid_swap_stats: {emoji: '⚡', color: '#06b6d4', title: 'Rapid swaps'},
    rune_transfer_stats: {emoji: '💸', color: '#84cc16', title: 'RUNE transfers'},
}

const UNKNOWN = {emoji: '📣', color: '#94a3b8'}

export function jobType(func) {
    return {...(JOB_TYPES[func] || {...UNKNOWN, title: func || 'unknown'}), func, known: func in JOB_TYPES}
}
