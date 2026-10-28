/* A small CSS reader for the "this change must look identical" tests (ds2-zero-change.test.mjs). No browser here, so the
   stylesheet text itself is compared: rules in load order, declarations, var() tokens expanded to their values. */

export function parse(css) {
  css = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const rules = [], frames = {};
  let order = 0;
  function splitTop(s, ch) {
    const out = []; let d = 0, q = null, cur = '';
    for (const c of s) {
      if (q) { cur += c; if (c === q) q = null; continue; }
      if (c === '"' || c === "'") { q = c; cur += c; continue; }
      if (c === '(' || c === '[') d++;
      if (c === ')' || c === ']') d--;
      if (c === ch && d === 0) { out.push(cur); cur = ''; } else cur += c;
    }
    out.push(cur);
    return out;
  }
  const decls = (body) => splitTop(body, ';').map((d) => d.trim()).filter(Boolean).map((d) => {
    const i = d.indexOf(':'); let v = d.slice(i + 1).trim(), important = false;
    if (/!\s*important\s*$/i.test(v)) { important = true; v = v.replace(/\s*!\s*important\s*$/i, '').trim(); }
    return { prop: d.slice(0, i).trim().toLowerCase(), value: v.replace(/\s+/g, ' '), important };
  });
  (function walk(s, media) {
    let i = 0;
    while (i < s.length) {
      const open = s.indexOf('{', i);
      if (open < 0) break;
      let depth = 1, j = open + 1;
      while (j < s.length && depth) { if (s[j] === '{') depth++; else if (s[j] === '}') depth--; j++; }
      const head = s.slice(i, open).trim().replace(/\s+/g, ' '), body = s.slice(open + 1, j - 1);
      if (/^@(media|supports|container|layer)\b/.test(head)) walk(body, media ? media + ' && ' + head : head);
      else if (/^@(-webkit-)?keyframes\b/.test(head)) frames[head.replace(/^@(-webkit-)?keyframes\s+/, '')] = body.replace(/\s+/g, ' ').trim();
      else if (!head.startsWith('@')) rules.push({ sel: head, parts: splitTop(head, ',').map((x) => x.trim().replace(/\s+/g, ' ')), decls: decls(body), media, order: order++ });
      i = j;
    }
  })(css, '');
  return { rules, frames };
}

/* every <style> block of an html page, in page order, as one sheet */
export function inlineStyles(html) {
  return [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n');
}

/* ---- tokens ---------------------------------------------------------------------------------------------------- */
/* custom properties of the skin root: `html.hb-apple` (light) and `html.hb-apple[data-theme="dark"]` laid over it */
export function tokenMaps(rules) {
  const light = {}, dark = {};
  for (const r of rules) {
    if (r.media) continue;
    for (const p of r.parts) {
      if (p !== 'html.hb-apple' && p !== 'html.hb-apple[data-theme="dark"]') continue;
      for (const d of r.decls) if (d.prop.startsWith('--')) (p === 'html.hb-apple' ? light : dark)[d.prop] = d.value;
    }
  }
  return { light, dark: { ...light, ...dark } };
}
export function resolve(value, map, depth = 0) {
  if (depth > 12) throw new Error('var() loop: ' + value);
  let out = value;
  for (let guard = 0; /var\(/.test(out) && guard < 40; guard++) {
    out = out.replace(/var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)/g, (m, name, fb) => (name in map ? resolve(map[name], map, depth + 1) : fb !== undefined ? fb.trim() : m));
    if (/var\(/.test(out) && !/var\(\s*--[\w-]+\s*(?:,[^()]*)?\)/.test(out)) break;
  }
  // calc(Apx + Bpx) / calc(Apx - Bpx) with plain numbers folds to one length
  out = out.replace(/calc\(\s*(-?[\d.]+)px\s*([+-])\s*(-?[\d.]+)px\s*\)/g, (m, a, op, b) => `${op === '+' ? +a + +b : +a - +b}px`);
  return out.replace(/\s+/g, ' ').trim();
}

/* ---- selectors ------------------------------------------------------------------------------------------------- */
function stripGroups(s) {            // drop :not(...) :is(...) :where(...) :has(...) and [attr] so only the compound's own tokens are left
  let out = '', i = 0;
  while (i < s.length) {
    const m = /^:(not|is|where|has)\(/.exec(s.slice(i));
    if (m) { let d = 1, j = i + m[0].length; while (j < s.length && d) { if (s[j] === '(') d++; else if (s[j] === ')') d--; j++; } i = j; continue; }
    if (s[i] === '[') { const j = s.indexOf(']', i); i = j < 0 ? s.length : j + 1; continue; }
    out += s[i++];
  }
  return out;
}
/* the last compound of a selector (what the rule styles); null when it ends in a pseudo-element */
export function subject(part) {
  let depth = 0, cut = 0;
  for (let i = 0; i < part.length; i++) {
    const c = part[i];
    if (c === '(' || c === '[') depth++;
    else if (c === ')' || c === ']') depth--;
    else if (depth === 0 && (c === ' ' || c === '>' || c === '+' || c === '~')) cut = i + 1;
  }
  const last = part.slice(cut).trim();
  return stripGroups(last).includes('::') ? null : last;
}
export function tokens(compound) { return new Set(stripGroups(compound).match(/[.#][\w-]+/g) || []); }

/* [ids, classes+attributes+pseudo-classes, elements] */
export function spec(part) {
  let s = part.replace(/:where\([^)]*\)/g, ''), a = 0, b = 0, c = 0;
  s = s.replace(/#[\w-]+/g, () => (a++, '')).replace(/\[[^\]]*\]/g, () => (b++, '')).replace(/::[\w-]+/g, () => (c++, ''))
    .replace(/:(not|is|has)\(([^)]*)\)/g, (m, f, inner) => { const t = spec(inner); a += t[0]; b += t[1]; c += t[2]; return ''; })
    .replace(/\.[\w-]+/g, () => (b++, '')).replace(/:[\w-]+/g, () => (b++, ''));
  c += (s.match(/(^|[\s>+~])[a-zA-Z][\w-]*/g) || []).length;
  return [a, b, c];
}
export const sameSpec = (x, y) => x[0] === y[0] && x[1] === y[1] && x[2] === y[2];

/* ---- proofs that a declaration never applies ------------------------------------------------------------------- */
const covers = (big, small) => big === small || small.startsWith(big + '-') ||
  (big === 'border-radius' && /^border-(top|bottom)-(left|right)-radius$/.test(small)) ||
  (big === 'padding-inline' && (small === 'padding-left' || small === 'padding-right'));

/* an !important rule of the skin root sheet for `.x` / `#x` beats any normal declaration on an element that has that class / id */
export function importantDominator(sysRules, part, prop) {
  if (!part.startsWith('html.hb-apple')) return null;
  const subj = subject(part);
  if (!subj) return null;
  const toks = tokens(subj);
  for (const r of sysRules) {
    if (r.media) continue;
    for (const d of r.decls) {
      if (!d.important || !covers(d.prop, prop)) continue;
      for (const p of r.parts) { const m = /^html\.hb-apple ([.#][\w-]+)$/.exec(p); if (m && toks.has(m[1])) return p; }
    }
  }
  return null;
}

/* a later rule with the very same selector (so the same specificity) that sets the property too, in every condition the victim applies in */
export function laterSameSelector(sheets, file, part, media, prop, order) {
  let seen = false;
  for (const sh of sheets) {
    for (const r of sh.rules) {
      if (sh.file === file && r.order <= order) continue;
      if (sh.file !== file && !seen) continue;
      if (r.media && r.media !== media) continue;
      if (!r.parts.includes(part)) continue;
      if (r.decls.some((d) => !d.important && covers(d.prop, prop) || d.prop === prop && !d.important)) return `${sh.file}#${r.order}`;
    }
    if (sh.file === file) seen = true;
  }
  return null;
}
