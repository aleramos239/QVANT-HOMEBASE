/* The Desk page as one text, for the tests that read its code: index.html with its run of /static/desk/*.js tags put back
   as the one inline <script> the code was until the split (2026-10-26) -- so every slice by a section comment still works.
   tests/desk_page_util.py is the same rule for the Python tests. */
import { readFileSync, readdirSync } from 'node:fs';
import assert from 'node:assert/strict';

const STATIC = new URL('../../homebase/static/', import.meta.url);
const read = (p) => readFileSync(new URL(p, STATIC), 'utf8');
const TAG = /<script src="\/static\/(desk\/[\w-]+\.js)\?v=\d+"><\/script>\n/g;
const page = read('index.html');
const files = [...page.matchAll(TAG)].map((m) => m[1]);
assert.deepEqual([...files].sort(), readdirSync(new URL('desk/', STATIC)).filter((f) => f.endsWith('.js')).map((f) => 'desk/' + f).sort(),
  'every static/desk/*.js has its tag in index.html, and no tag names a missing file');
export const HTML = page.replace(new RegExp(`(?:${TAG.source})+`), () => '<script>\n' + files.map(read).join('') + '</script>\n');
