// Lightning bolts in place of the route arrows of the swap cards (templates/components/bolt.jinja2).
// Every <svg class="bolt"> carries its direction (right, left, down), kind (main, refund, pending) and a seed:
// the same swap always gets the same bolts. A bolt runs along "t" (0..L) and swings across along "u".
(function () {
    const NS = 'http://www.w3.org/2000/svg';

    const PALETTES = {
        main: {from: '#33FF99', to: '#00CCFF', mid: '#23DCC8', core: '#ffffff', opacity: 1},
        refund: {from: '#ffb03d', to: '#ff3355', mid: '#ff6a5c', core: '#fff1ea', opacity: 1},
        pending: {from: '#55636d', to: '#8796a0', mid: '#6d7c86', core: '#c4ced4', opacity: 0.7},
    };

    const ROUND = {'stroke-linecap': 'round', 'stroke-linejoin': 'round', fill: 'none'};

    function rng(text) {
        // mulberry32 seeded by FNV-1a of the text
        let seed = 2166136261;
        for (const ch of text) seed = Math.imul(seed ^ ch.charCodeAt(0), 16777619);
        return () => {
            seed = (seed + 0x6D2B79F5) | 0;
            let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }

    function el(parent, tag, attrs = {}) {
        const node = document.createElementNS(NS, tag);
        for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
        parent.appendChild(node);
        return node;
    }

    // midpoint displacement: a jagged line from a to b
    function jag(rnd, a, b, disp, depth) {
        if (depth <= 0) return [a, b];
        const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
        const off = (rnd() - 0.5) * disp;
        const m = [(a[0] + b[0]) / 2 - dy / len * off, (a[1] + b[1]) / 2 + dx / len * off];
        return jag(rnd, a, m, disp / 2, depth - 1).concat(jag(rnd, m, b, disp / 2, depth - 1).slice(1));
    }

    // a sharp zigzag from a to b: the kinks go to alternate sides, smaller near the ends, and every stroke is a bit jagged
    function zigzag(rnd, a, b, amp, kinks) {
        const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
        const pts = [a];
        let side = rnd() < 0.5 ? -1 : 1;
        for (let i = 1; i <= kinks; i++) {
            const k = (i + (rnd() - 0.5) * 0.7) / (kinks + 1);
            const off = side * amp * (0.55 + rnd() * 0.45) * Math.sqrt(Math.sin(Math.PI * k));
            pts.push([a[0] + dx * k - dy / len * off, a[1] + dy * k + dx / len * off]);
            side = -side;
        }
        pts.push(b);
        let out = [a];
        for (let i = 1; i < pts.length; i++) {
            const seg = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
            out = out.concat(jag(rnd, pts[i - 1], pts[i], seg * 0.18, 2).slice(1));
        }
        return out;
    }

    function polyline(c, pts) {
        return 'M' + pts.map(([t, u]) => c.p(t, u).map(n => n.toFixed(1)).join(' ')).join('L');
    }

    // a neon line: a wide soft halo, a tight glow and a hot core
    function neon(c, d, width, color = c.grad) {
        el(c.svg, 'path', {...ROUND, d, stroke: color, 'stroke-width': width * 4, opacity: 0.75, filter: `url(#${c.id}l)`});
        el(c.svg, 'path', {...ROUND, d, stroke: color, 'stroke-width': width * 2, filter: `url(#${c.id}s)`});
        el(c.svg, 'path', {...ROUND, d, stroke: color, 'stroke-width': width * 1.2});
        el(c.svg, 'path', {...ROUND, d, stroke: c.pal.core, 'stroke-width': width * 0.55});
    }

    function sparkle(c, t, u, r, opacity) {
        const [x, y] = c.p(t, u), w = r * 0.18;
        const d = `M${x} ${y - r}L${x + w} ${y - w}L${x + r} ${y}L${x + w} ${y + w}L${x} ${y + r}L${x - w} ${y + w}L${x - r} ${y}L${x - w} ${y - w}Z`;
        el(c.svg, 'path', {d, fill: c.pal.mid, opacity, filter: `url(#${c.id}s)`});
        el(c.svg, 'path', {d, fill: c.pal.core, opacity});
    }

    function orb(c, t, u, r, opacity = 1) {
        const [cx, cy] = c.p(t, u);
        el(c.svg, 'circle', {cx, cy, r, fill: `url(#${c.id}r)`, opacity});
    }

    function drawBolt(svg, index) {
        const W = +svg.getAttribute('width'), H = +svg.getAttribute('height');
        const {dir = 'right', kind = 'main', seed = ''} = svg.dataset;
        if (!W || !H) return;
        const pal = PALETTES[kind] || PALETTES.main;
        const L = dir === 'down' ? H : W, T = dir === 'down' ? W : H;
        const p = dir === 'down' ? (t, u) => [W / 2 - u, t]
            : dir === 'left' ? (t, u) => [W - t, H / 2 + u]
                : (t, u) => [t, H / 2 + u];
        const id = `bolt${index}`;
        const defs = el(svg, 'defs');
        const [x1, y1] = p(0, 0), [x2, y2] = p(L, 0);
        const grad = el(defs, 'linearGradient', {id: `${id}g`, gradientUnits: 'userSpaceOnUse', x1, y1, x2, y2});
        el(grad, 'stop', {offset: 0, 'stop-color': pal.from});
        el(grad, 'stop', {offset: 1, 'stop-color': pal.to});
        const radial = el(defs, 'radialGradient', {id: `${id}r`});
        el(radial, 'stop', {offset: 0, 'stop-color': pal.core});
        el(radial, 'stop', {offset: 0.25, 'stop-color': pal.to, 'stop-opacity': 0.8});
        el(radial, 'stop', {offset: 1, 'stop-color': pal.to, 'stop-opacity': 0});
        for (const [name, std] of [['s', 2], ['l', 10]]) {
            const f = el(defs, 'filter', {id: `${id}${name}`, filterUnits: 'userSpaceOnUse', x: -300, y: -300, width: W + 600, height: H + 600});
            el(f, 'feGaussianBlur', {stdDeviation: std});
        }
        svg.style.opacity = pal.opacity;

        const c = {svg, p, pal, id, grad: `url(#${id}g)`};
        const rnd = rng(`${seed}|${dir}|${kind}|${index}`);
        const kinks = Math.max(2, Math.round(L / 40));
        // sparks fly around a full bolt, not around the thin halves of a refund or the one down to the affiliates
        if (L >= 150 && T >= 60) {
            for (let i = 0; i < 7; i++) sparkle(c, L * rnd(), (rnd() - 0.5) * T * 1.5, 3 + rnd() * 4, 0.5 + rnd() * 0.5);
        }
        // a wide bolt is a bundle: two side strikes swing wider than the main one and meet it at the ends
        if (T >= 40) {
            // with fewer and wider kinks, so the three do not weave into a net
            for (const [color, amp] of [[pal.from, 0.6], [pal.to, 0.5]]) {
                neon(c, polyline(c, zigzag(rnd, [0, 0], [L, 0], T * amp, kinks - 2 + Math.floor(rnd() * 2))), 2.2, color);
            }
        }
        const main = zigzag(rnd, [0, 0], [L, 0], T * 0.36, kinks);
        const branches = (T >= 40 ? 3 : 2) + Math.floor(rnd() * 2);
        for (let i = 0; i < branches; i++) {
            const s = main[Math.floor((0.12 + rnd() * 0.55) * main.length)];
            const angle = (rnd() < 0.5 ? -1 : 1) * (0.35 + rnd() * 0.45), len = L * (0.14 + rnd() * 0.18);
            const e = [s[0] + Math.cos(angle) * len, s[1] + Math.sin(angle) * len * 0.8];
            neon(c, polyline(c, zigzag(rnd, s, e, len * 0.2, 2)), T > 40 ? 2.2 : 1.1);
        }
        neon(c, polyline(c, main), T > 40 ? 5 : 2.4);
        orb(c, 0, 0, T * 0.4, 0.8);
        orb(c, L, 0, T * 0.6);
    }

    document.querySelectorAll('svg.bolt').forEach(drawBolt);
})();
