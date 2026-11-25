/* Orthogonal arrow router for the architecture map.
 *
 * Guarantees, for the boxes and arrows it is given:
 *   - every arrow has its own start point and its own end point (ports are never shared);
 *   - no two arrows run along the same line (parallel runs keep at least 2 grid steps apart);
 *   - no arrow passes through a box (arrows may cross each other, at a cost).
 * It routes on a grid (A* with a cost for bends, crossings and hugging boxes), solid arrows
 * first, then background ones, then later ones. Used by index.html, and by tools/arrows.py
 * (through node) to check every fold state.
 */
(function (root) {
  "use strict";
  const DX = [1, -1, 0, 0], DY = [0, 0, 1, -1];        // 0 E, 1 W, 2 S, 3 N
  const BEND = 14, CROSS = 5, NEAR = 2, PORT_GAP = 3;   // costs; PORT_GAP in grid steps

  function route(opts) {
    const G = opts.step || 5;
    const C = Math.floor(opts.w / G) + 1, R = Math.floor(opts.h / G) + 1, N = C * R;
    const box = new Int16Array(N).fill(-1);   // which box a cell is inside (inflated)
    const near = new Uint8Array(N);
    const usedH = new Uint8Array(N), usedV = new Uint8Array(N), port = new Uint8Array(N);
    const boxes = opts.boxes;
    const idx = (c, r) => r * C + c;
    const inside = (c, r) => c >= 0 && r >= 0 && c < C && r < R;

    boxes.forEach((b, bi) => {
      for (let r = Math.max(0, Math.floor((b.y - 3) / G)); r <= Math.min(R - 1, Math.ceil((b.y + b.h + 3) / G)); r++)
        for (let c = Math.max(0, Math.floor((b.x - 3) / G)); c <= Math.min(C - 1, Math.ceil((b.x + b.w + 3) / G)); c++) {
          const x = c * G, y = r * G;
          if (x >= b.x - 3 && x <= b.x + b.w + 3 && y >= b.y - 3 && y <= b.y + b.h + 3) box[idx(c, r)] = bi;
        }
      for (let r = Math.max(0, Math.floor((b.y - 10) / G)); r <= Math.min(R - 1, Math.ceil((b.y + b.h + 10) / G)); r++)
        for (let c = Math.max(0, Math.floor((b.x - 10) / G)); c <= Math.min(C - 1, Math.ceil((b.x + b.w + 10) / G)); c++) near[idx(c, r)] = 1;
    });

    // the cells just outside each side of a box, with the direction that leaves it
    function ports(bi) {
      const b = boxes[bi], out = [];
      const margin = Math.min(10, b.w / 3, b.h / 3);
      const cL = Math.ceil((b.x - 3) / G) - 1, cR = Math.floor((b.x + b.w + 3) / G) + 1;
      const rT = Math.ceil((b.y - 3) / G) - 1, rB = Math.floor((b.y + b.h + 3) / G) + 1;
      for (let r = Math.ceil((b.y + margin) / G); r * G <= b.y + b.h - margin; r++) {
        out.push({ c: cL, r, dir: 1, edge: [b.x, r * G], off: Math.abs(r * G - (b.y + b.h / 2)) });
        out.push({ c: cR, r, dir: 0, edge: [b.x + b.w, r * G], off: Math.abs(r * G - (b.y + b.h / 2)) });
      }
      for (let c = Math.ceil((b.x + margin) / G); c * G <= b.x + b.w - margin; c++) {
        out.push({ c, r: rT, dir: 3, edge: [c * G, b.y], off: Math.abs(c * G - (b.x + b.w / 2)) });
        out.push({ c, r: rB, dir: 2, edge: [c * G, b.y + b.h], off: Math.abs(c * G - (b.x + b.w / 2)) });
      }
      return out.filter(p => inside(p.c, p.r) && box[idx(p.c, p.r)] === -1 && !port[idx(p.c, p.r)]);
    }

    function search(src, dst, strict) {
      const S = ports(src), T = ports(dst);
      if (!S.length || !T.length) return null;
      const goal = new Map();
      T.forEach(p => goal.set(idx(p.c, p.r), p));
      const tb = boxes[dst], tcx = tb.x + tb.w / 2, tcy = tb.y + tb.h / 2;
      const h = (c, r) => (Math.max(0, Math.abs(c * G - tcx) - tb.w / 2) + Math.max(0, Math.abs(r * G - tcy) - tb.h / 2)) / G;
      const M = N * 4, g = new Float64Array(M).fill(Infinity), prev = new Int32Array(M).fill(-1);
      const heap = [];
      const push = (f, s) => { heap.push([f, s]); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
      const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } } return top; };
      const startOf = new Map();
      S.forEach(p => { const s = idx(p.c, p.r) * 4 + p.dir, cost = p.off / G * 0.3; if (cost < g[s]) { g[s] = cost; startOf.set(s, p); push(cost + h(p.c, p.r), s); } });
      while (heap.length) {
        const [f, s] = pop();
        const cell = s >> 2, d = s & 3, cost = g[s];
        if (f - h(cell % C, (cell / C) | 0) > cost + 1e-6) continue;
        const gp = goal.get(cell);
        if (gp && d === [1, 0, 3, 2][gp.dir]) return { s, gp, prev, startOf };
        const c = cell % C, r = (cell / C) | 0;
        for (let nd = 0; nd < 4; nd++) {
          if (nd === [1, 0, 3, 2][d]) continue;          // no U-turns
          const nc = c + DX[nd], nr = r + DY[nd];
          if (!inside(nc, nr)) continue;
          const n = idx(nc, nr);
          if (box[n] !== -1) continue;
          const horiz = nd < 2;
          let step = 1 + (near[n] ? NEAR : 0) + (nd !== d ? BEND : 0);
          if (horiz ? usedH[n] : usedV[n]) { if (strict) continue; step += 60; }
          if (horiz ? usedH[cell] : usedV[cell]) { if (strict) continue; step += 60; }
          if (horiz ? usedV[n] : usedH[n]) step += CROSS;
          if (port[n] && !goal.has(n)) { if (strict) continue; step += 60; }
          const ns = n * 4 + nd, ng = cost + step;
          if (ng < g[ns]) { g[ns] = ng; prev[ns] = s; push(ng + h(nc, nr), ns); }
        }
      }
      return null;
    }

    function claim(cells) {
      for (let i = 0; i < cells.length; i++) {
        const [c, r] = cells[i];
        const a = cells[i - 1], b = cells[i + 1];
        const h = (a && a[1] === r) || (b && b[1] === r), v = (a && a[0] === c) || (b && b[0] === c);
        for (let k = -1; k <= 1; k++) {
          if (h && inside(c, r + k)) usedH[idx(c, r + k)] = 1;
          if (v && inside(c + k, r)) usedV[idx(c + k, r)] = 1;
        }
      }
    }
    function claimPort(p, side) {
      for (let k = -PORT_GAP; k <= PORT_GAP; k++) {
        const c = side < 2 ? p.c : p.c + k, r = side < 2 ? p.r + k : p.r;
        if (inside(c, r)) port[idx(c, r)] = 1;
      }
    }

    const order = opts.edges.map((e, i) => ({ e, i, rank: e.kind === "fut" ? 2 : e.kind === "bg" ? 1 : 0 }))
      .sort((a, b) => a.rank - b.rank || a.i - b.i);
    const result = new Array(opts.edges.length).fill(null);
    const failed = [];
    for (const { e, i } of order) {
      const src = boxes.findIndex(b => b.id === e.from), dst = boxes.findIndex(b => b.id === e.to);
      if (src < 0 || dst < 0 || src === dst) { failed.push(e.id); continue; }
      let found = search(src, dst, true), strict = true;
      if (!found) { found = search(src, dst, false); strict = false; }
      if (!found) { failed.push(e.id); continue; }
      const { s, gp, prev, startOf } = found;
      const cells = [];
      let x = s, first = s;
      while (x !== -1) { cells.push([(x >> 2) % C, ((x >> 2) / C) | 0]); first = x; x = prev[x]; }
      cells.reverse();
      const sp = startOf.get(first);
      claim(cells);
      claimPort(sp, sp.dir); claimPort(gp, gp.dir);
      // corner points: start on the box edge, every bend, end on the box edge
      const pts = [sp.edge];
      for (let k = 0; k < cells.length; k++) {
        const a = cells[k - 1], b = cells[k], c2 = cells[k + 1];
        if (!a || !c2) { pts.push([b[0] * G, b[1] * G]); continue; }
        if ((a[0] === b[0]) !== (b[0] === c2[0])) pts.push([b[0] * G, b[1] * G]);
      }
      pts.push(gp.edge);
      const clean = pts.filter((p, k) => k === 0 || p[0] !== pts[k - 1][0] || p[1] !== pts[k - 1][1]);
      const keep = clean.filter((p, k) => k === 0 || k === clean.length - 1 ||
        !((clean[k - 1][0] === p[0] && p[0] === clean[k + 1][0]) || (clean[k - 1][1] === p[1] && p[1] === clean[k + 1][1])));
      let d = "M" + keep[0][0] + "," + keep[0][1];
      for (let k = 1; k < keep.length; k++) d += keep[k][1] === keep[k - 1][1] ? " H" + keep[k][0] : " V" + keep[k][1];
      // label: middle of the longest run
      let best = null;
      for (let k = 1; k < keep.length; k++) {
        const len = Math.abs(keep[k][0] - keep[k - 1][0]) + Math.abs(keep[k][1] - keep[k - 1][1]);
        if (!best || len > best.len) best = { len, a: keep[k - 1], b: keep[k] };
      }
      const horiz = best.a[1] === best.b[1];
      const label = horiz ? { x: (best.a[0] + best.b[0]) / 2, y: best.a[1] - 5, anchor: "middle" }
        : { x: best.a[0] - 5, y: (best.a[1] + best.b[1]) / 2, rotate: -90, anchor: "middle" };
      result[i] = { d, label, strict };
      if (!strict) failed.push(e.id + " (shares a line)");
    }
    return { routes: result, failed };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { route };
  else root.KotlRouter = { route };
})(this);
