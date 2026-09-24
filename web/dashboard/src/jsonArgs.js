// Parsing of the "job arguments" JSON fields with a readable, position-aware error.

function lineColumn(text, position) {
    const before = text.slice(0, position)
    const line = before.split('\n').length
    const column = position - before.lastIndexOf('\n')
    return {line, column}
}

function describeError(e, text) {
    const msg = String(e?.message || e)
    // V8 (Chrome, Node): "... at position 14 (line 3 column 3)"; Firefox: "... at line 3 column 3 of the JSON data"
    let m = msg.match(/line (\d+) column (\d+)/)
    if (m) return {message: msg.replace(/\s*\(?at (position \d+ \()?line \d+ column \d+.*$/, ''), line: +m[1], column: +m[2]}
    m = msg.match(/position (\d+)/)
    if (m) return {message: msg.replace(/\s*at position \d+.*$/, ''), ...lineColumn(text, +m[1])}
    return {message: msg}
}

/**
 * {value} for a JSON object (empty text counts as {}), or {error: 'message (line 3, column 3)'}.
 */
export function parseJsonObject(text) {
    const source = (text || '').trim()
    if (!source) return {value: {}}
    let value
    try {
        value = JSON.parse(source)
    } catch (e) {
        const {message, line, column} = describeError(e, source)
        return {error: line ? `${message} (line ${line}, column ${column})` : message}
    }
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return {error: 'Arguments must be a JSON object, like {"days": 7}'}
    }
    return {value}
}
