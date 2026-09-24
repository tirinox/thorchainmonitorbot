// Renders Telegram-flavoured HTML (what the bot posts) safely: everything is escaped first, then only the tags
// Telegram itself supports are let back in, and links only for http(s) URLs.

const ALLOWED_TAGS = ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'code', 'pre', 'blockquote',
    'tg-spoiler']

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
}

export function telegramHtml(text) {
    let html = escapeHtml(text || '')
    for (const tag of ALLOWED_TAGS) {
        html = html.replace(new RegExp(`&lt;(/?)${tag}&gt;`, 'gi'), `<$1${tag}>`)
    }
    // <pre><code class="language-x"> blocks
    html = html.replace(/&lt;code class=&quot;language-([\w-]+)&quot;&gt;/gi, '<code class="language-$1">')
    html = html.replace(/&lt;a href=&quot;(https?:\/\/.*?)&quot;&gt;/gi,
        '<a href="$1" target="_blank" rel="noopener noreferrer">')
    html = html.replace(/&lt;\/a&gt;/gi, '</a>')
    return html
}
