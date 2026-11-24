// Routes the architecture map's arrows in every fold state (as index.html does) and prints the
// result as JSON for tools/arrows.py. Usage: node tools/arrows-check.js docs/architecture
const path = require("path");
const dir = path.resolve(process.argv[2] || "docs/architecture");
const { route } = require(path.join(dir, "router.js"));
const A = require(path.join(dir, "architecture.json"));

const GINDEX = {}, NODE_GROUP = {}, KEEP = new Set();
const key = n => n.detail || n.id;
(function walk(list, parent) {
  list.forEach(g => {
    GINDEX[g.id] = { g, parent };
    (g.keep || []).forEach(k => KEEP.add(k));
    (g.items || []).forEach(i => A.nodes.filter(n => n.id === i || key(n) === i).forEach(n => { NODE_GROUP[n.id] = g.id; }));
    walk(g.children || [], g.id);
  });
})(A.groups || [], null);
const groupNodes = gid => A.nodes.filter(n => NODE_GROUP[n.id] === gid).map(n => n.id)
  .concat(...(GINDEX[gid].g.children || []).map(c => groupNodes(c.id)));
const foldable = Object.values(GINDEX).filter(x => x.g.collapse).map(x => x.g);
const rectOf = g => {
  if (g.collapse === "chip") return g.chip;
  const ns = A.nodes.filter(n => groupNodes(g.id).includes(n.id));
  const x = Math.min(...ns.map(n => n.x)), y = Math.min(...ns.map(n => n.y));
  return { x, y, w: Math.max(...ns.map(n => n.x + n.w)) - x, h: Math.max(...ns.map(n => n.y + n.h)) - y };
};

const out = [];
for (let mask = 0; mask < 1 << foldable.length; mask++) {
  const folded = new Set(foldable.filter((g, i) => mask & (1 << i)).map(g => g.id));
  const hiddenBy = id => {
    if (KEEP.has(id)) return null;
    let f = null;
    for (let g = NODE_GROUP[id]; g; g = GINDEX[g].parent) if (folded.has(g)) f = g;
    return f;
  };
  const boxes = A.nodes.filter(n => !hiddenBy(n.id)).map(n => ({ id: n.id, x: n.x, y: n.y, w: n.w, h: n.h }));
  foldable.forEach(g => {
    let p = GINDEX[g.id].parent, outer = false;
    for (; p; p = GINDEX[p].parent) if (folded.has(p)) outer = true;
    if (folded.has(g.id) && !outer) boxes.push(Object.assign({ id: "g:" + g.id }, rectOf(g)));
  });
  const vis = id => { const g = hiddenBy(id); return g ? "g:" + g : id; };
  const pairs = {}, list = [];
  A.edges.forEach(e => {
    const a = vis(e.from), b = vis(e.to);
    if (a === b || (e.style === "fut" && (a !== e.from || b !== e.to))) return;
    const k = a + ">" + b;
    if (!pairs[k]) { pairs[k] = { id: e.id, from: a, to: b, kind: e.style || "solid" }; list.push(pairs[k]); }
    else pairs[k].id += "+" + e.id;
  });
  const r = route({ w: A.canvas.w, h: A.canvas.h, step: 5, boxes, edges: list });
  out.push({ folded: [...folded], failed: r.failed, boxes, edges: list.map((e, i) => ({ id: e.id, d: r.routes[i] ? r.routes[i].d : null })) });
}
console.log(JSON.stringify(out));
