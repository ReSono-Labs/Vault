#!/usr/bin/env node
/**
 * Generates styles/browser-voice-aurora.generated.css: an Aurora (light) override for EVERY
 * colour declaration in the app's stylesheets, so no element keeps a Midnight colour.
 *
 *   node scripts/build-aurora-theme.mjs        (run after changing any app CSS)
 *
 * Mapping rules (Midnight -> Aurora):
 * - neutral and navy surfaces/text invert lightness (dark glass -> white glass, light text -> ink);
 * - cyan/teal accents -> pink, sky/blue accents -> violet; warning red, success green, sun yellow kept;
 * - shadows become soft lilac instead of inverting to white.
 * Hand-tuned surfaces (aurora background, glass, pills) live in browser-voice-aurora.css, loaded after.
 */
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import postcss from "postcss";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "browser-voice");
const PREFIX = ':root[data-theme="aurora"]';
const SKIP = new Set(["browser-voice-aurora.generated.css", "browser-voice-aurora.css", "genui.css"]);
const COLOR = /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|rgba?\([^)]*\)|\b(?:white|black)\b/g;
const SHADOW_PROPS = /shadow|filter/;
const LINE_PROPS = /^(border|outline|stroke|column-rule|text-decoration-color|caret-color)/;

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? files(join(dir, entry.name)) : entry.name.endsWith(".css") && !SKIP.has(entry.name) ? [join(dir, entry.name)] : []);
}
function parse(token) {
  if (token === "white") return [255, 255, 255, 1];
  if (token === "black") return [0, 0, 0, 1];
  if (token[0] === "#") {
    let hex = token.slice(1);
    if (hex.length <= 4) hex = [...hex].map(c => c + c).join("");
    const n = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
    return [...n, hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1];
  }
  const parts = token.replace(/rgba?\(|\)/g, "").split(/[\s,/]+/).filter(Boolean).map(Number);
  return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
}
function hsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min, s = l > .5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s, l];
}
const rgba = (r, g, b, a) => a >= 1 ? `rgb(${r} ${g} ${b})` : `rgba(${r}, ${g}, ${b}, ${+a.toFixed(3)})`;

/** Custom properties take the role their name implies. */
function role(prop) {
  if (!prop.startsWith("--")) return prop;
  if (/shadow/.test(prop)) return "box-shadow";
  if (/line|border|edge|ring/.test(prop)) return "border-color";
  if (/text|ink|muted|fg/.test(prop)) return "color";
  return "background";
}

/** Map one colour for a property. */
function mapColor(token, rawProp) {
  const prop = role(rawProp);
  const [r, g, b, a] = parse(token);
  const [h, s, l] = hsl([r, g, b]);
  if (SHADOW_PROPS.test(prop)) {  // Shadows stay shadows: soft lilac, lighter.
    if (l < .5) return rgba(90, 50, 120, Math.min(a * .45, .22));
    return rgba(255, 255, 255, Math.min(a, .7));
  }
  const accent = s > .45 && l > .3 && l < .85;
  if (accent) {
    if (h >= 150 && h < 195) return rgba(236, 63, 122, a);        // mint/cyan -> pink
    if (h >= 195 && h < 250) return rgba(154, 108, 240, a);       // sky/blue  -> violet
    if (h < 20 || h >= 340) return rgba(Math.round(r * .85), Math.round(g * .6), Math.round(b * .6), a); // warn red, deeper
    if (h >= 40 && h < 65) return rgba(214, 160, 0, a);           // sun yellow, readable on light
    if (h >= 95 && h < 150) return rgba(19, 138, 94, a);          // success green
    return rgba(r, g, b, a);
  }
  // Neutral / navy: invert lightness, warm it slightly.
  if (LINE_PROPS.test(prop)) return l > .5 ? rgba(18, 18, 22, Math.min(a * .75, .16)) : rgba(255, 255, 255, Math.min(a + .3, .9));
  const isText = prop === "color" || prop === "fill" || prop === "-webkit-text-fill-color";
  if (isText) {
    if (l > .55) return a < .7 || l < .8 ? rgba(74, 74, 85, Math.max(a, .9)) : rgba(18, 18, 22, a);  // muted vs primary ink
    return rgba(255, 255, 255, a);                                 // dark text was on a light chip -> white on dark
  }
  // Backgrounds and other paints.
  if (l < .3) return a < .5 ? rgba(255, 255, 255, Math.min(a * 1.6 + .25, .85)) : rgba(255, 255, 255, .62 + .3 * a * (.3 - l));
  if (l > .8) return a < .35 ? rgba(18, 18, 22, Math.min(a * .7, .08)) : rgba(22, 22, 27, a);      // light tint -> faint ink; light chip -> black pill
  return rgba(255, 255, 255, Math.min(.5 + a * .4, .9));
}

function scope(selector) {
  return selector.split(",").map(part => {
    const s = part.trim();
    if (/^(:root|html)\b/.test(s)) return s.replace(/^(:root|html)/, PREFIX);
    if (/^body\b/.test(s)) return `${PREFIX} ${s}`;
    if (s.startsWith("::") || s === "*") return `${PREFIX} ${s}`;
    return `${PREFIX} ${s}`;
  }).join(",\n");
}

const out = postcss.root();
let count = 0;
for (const file of files(root).sort()) {
  const css = postcss.parse(readFileSync(file, "utf8"), { from: file });
  css.walkRules(rule => {
    if (rule.parent?.type === "atrule" && /keyframes/.test(rule.parent.name)) return;
    const decls = [];
    rule.each(node => {
      if (node.type !== "decl" || node.prop.startsWith("--") && !COLOR.test(node.value)) return;
      COLOR.lastIndex = 0;
      if (!COLOR.test(node.value)) return;
      COLOR.lastIndex = 0;
      decls.push(postcss.decl({ prop: node.prop, value: node.value.replace(COLOR, t => mapColor(t, node.prop)), important: node.important }));
    });
    if (!decls.length) return;
    const clone = postcss.rule({ selector: scope(rule.selector) });
    decls.forEach(d => clone.append(d));
    let target = out;
    // Recreate enclosing @media/@supports wrappers.
    const chain = [];
    for (let p = rule.parent; p && p.type === "atrule"; p = p.parent) chain.unshift(p);
    for (const at of chain) {
      const wrapper = postcss.atRule({ name: at.name, params: at.params });
      target.append(wrapper); target = wrapper;
    }
    target.append(clone);
    count += decls.length;
  });
}
const header = `/* GENERATED by scripts/build-aurora-theme.mjs — do not edit. ${count} colour declarations. */\n`;
writeFileSync(join(root, "styles", "browser-voice-aurora.generated.css"), header + out.toString() + "\n");
console.log(`aurora: ${count} declarations`);
