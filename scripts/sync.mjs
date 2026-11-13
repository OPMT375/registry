// Sync: copies what every team has committed into the shared chain database.
//
// Each team's repo is its own system of record. This script reads, for every team in teams/*.json:
//   domain.json         parties (sites, named by GLN) and products (named by GTIN)
//   capabilities.json   what the firm can promise
//   metrics.json        how the firm will measure itself
//   signals/*.json      orders, acknowledgements, forecasts, alerts (one file per signal)
//   events/*.json       shipping, receiving and other critical tracking events (one file per event)
// and writes them to the class Supabase database. Anything it cannot accept is written to
// sync_issues with a plain-English reason, and shows on the chain page.
//
// Rules it enforces (the identity lessons from the network segment):
//   - A team may only create GLNs and GTINs that start with its assigned prefix.
//   - A team may only send signals from, and record events at, its own parties.
//   - A signal or event, once synced, is permanent. Edits are ignored; send a correction instead.
//   - sent_at is the time the file first reached the repo (the commit), not a date the team types.
//
// Usage:  SUPABASE_DB_URL=postgres://... [GITHUB_TOKEN=...] node scripts/sync.mjs [--team <slug>] [--dry-run]
// Test:   LOCAL_REPOS=/path/to/dir  (clones <dir>/<owner>__<repo> instead of GitHub)
import fs from 'fs';
import os from 'os';
import path from 'path';
import { execFileSync } from 'child_process';
import pg from 'pg';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const args = process.argv.slice(2);
const onlyTeam = args.includes('--team') ? args[args.indexOf('--team') + 1] : null;
const dryRun = args.includes('--dry-run');
const DB_URL = process.env.SUPABASE_DB_URL;
const TOKEN = process.env.GITHUB_TOKEN;
const LOCAL = process.env.LOCAL_REPOS;
if (!DB_URL) { console.error('Set SUPABASE_DB_URL (Supabase → Project Settings → Database → connection string).'); process.exit(1); }

const issues = [];
const issue = (team, file, message, level = 'error') => issues.push({ team, file, message, level });
const count = {};
const bump = (team, k) => { count[team] ??= {}; count[team][k] = (count[team][k] || 0) + 1; };

// ---------- read the registry ----------
const assignments = JSON.parse(fs.readFileSync(path.join(root, 'assignments.json'), 'utf8'));
const teams = fs.readdirSync(path.join(root, 'teams'))
  .filter(f => f.endsWith('.json') && f !== 'example-team.json')
  .map(f => ({ slug: f.replace(/\.json$/, ''), ...JSON.parse(fs.readFileSync(path.join(root, 'teams', f), 'utf8')) }))
  .filter(t => !onlyTeam || t.slug === onlyTeam)
  .map(t => ({ ...t, prefix: assignments.teams?.[t.slug]?.gln_prefix || null }));

// ---------- read each team repo ----------
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'chain-sync-'));
const git = (cwd, ...a) => execFileSync('git', a, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
const loginCache = new Map();

async function loginFor(repo, sha, email, name) {
  if (loginCache.has(sha)) return loginCache.get(sha);
  let login = null;
  if (TOKEN && !LOCAL) {
    try {
      const r = await fetch(`https://api.github.com/repos/${repo}/commits/${sha}`, {
        headers: { Authorization: `Bearer ${TOKEN}`, Accept: 'application/vnd.github+json' },
      });
      if (r.ok) login = (await r.json()).author?.login || null;
    } catch { /* fall through */ }
  }
  if (!login) { const m = /^(?:\d+\+)?([A-Za-z0-9-]+)@users\.noreply\.github\.com$/.exec(email || ''); if (m) login = m[1]; }
  login ??= name || null;
  loginCache.set(sha, login);
  return login;
}

function cloneTeam(t) {
  const dir = path.join(work, t.slug);
  const src = LOCAL ? path.join(LOCAL, t.repo.replace('/', '__')) : `https://github.com/${t.repo}.git`;
  const cloneArgs = LOCAL ? ['clone', '--quiet', src, dir] : ['clone', '--quiet', '--filter=blob:none', src, dir];
  execFileSync('git', cloneArgs, { stdio: ['ignore', 'ignore', 'pipe'] });
  return dir;
}

function readJson(t, dir, rel) {
  const p = path.join(dir, rel);
  if (!fs.existsSync(p)) return undefined;
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); }
  catch (e) { issue(t.slug, rel, `is not valid JSON (${e.message}). Look for a missing comma, quote or bracket.`); return null; }
}

// First commit that added a file: when it was "sent", and by whom.
async function firstCommit(t, dir, rel) {
  const lines = git(dir, 'log', '--diff-filter=A', '--format=%H|%cI|%ae|%an', '--', rel).split('\n').filter(Boolean);
  if (!lines.length) return { at: new Date().toISOString(), by: null };
  const [sha, at, email, name] = lines[lines.length - 1].split('|');
  return { at, by: await loginFor(t.repo, sha, email, name) };
}

function listJsonFiles(dir, folder) {
  const d = path.join(dir, folder);
  if (!fs.existsSync(d)) return [];
  return fs.readdirSync(d).filter(f => f.endsWith('.json') && !f.startsWith('_')).sort().map(f => `${folder}/${f}`);
}

// Master-data lists can live in one file (capabilities.json → "capabilities": [...]) or as one file per item in a
// folder (capabilities/receive-corn.json), which lets each teammate commit their own item without edit conflicts.
// In a folder, the file name is the id unless the file sets one. If any file is broken, nothing is deleted this run.
function collect(t, dir, file, key, folder) {
  const out = { found: false, broken: false, items: [] };
  const whole = readJson(t, dir, file);
  if (whole === null) out.broken = true;
  if (whole !== undefined) out.found = true;
  if (whole) for (const [i, item] of (whole[key] || []).entries()) out.items.push({ at: `${file} ${key}[${i}]`, item });
  for (const rel of listJsonFiles(dir, folder)) {
    out.found = true;
    const item = readJson(t, dir, rel);
    if (!item) { out.broken = true; continue; }
    out.items.push({ at: rel, item: { id: path.basename(rel, '.json'), ...item } });
  }
  return out;
}

// ---------- helpers ----------
const GLN = /^[0-9]{13}$/;
const GTIN = /^[0-9]{14}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ID = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const SCOR = ['plan', 'source', 'make', 'deliver', 'return', 'enable'];
const PERIODS = ['hour', 'day', 'week', 'month'];
const ATTRS = ['reliability', 'responsiveness', 'agility', 'cost', 'assets'];
const EVENT_TYPES = ['harvest', 'cooling', 'initial_packing', 'shipping', 'receiving', 'transformation'];
const SIGNAL_TYPES = ['order', 'acknowledgement', 'forecast', 'alert'];
const num = v => (v === undefined || v === null || v === '' ? null : Number(v));
const str = v => (v === undefined || v === null || String(v).trim() === '' ? null : String(v).trim());

function plainDbError(e) {
  const d = e.detail || '';
  let m = /Key \((\w+)\)=\(([^)]*)\) is not present in table "(\w+)"/.exec(d);
  if (m) {
    const what = { parties: 'a party (GLN)', products: 'a product (GTIN)', lots: 'a lot', signals: 'a signal', teams: 'a team' }[m[3]] || m[3];
    return `"${m[2]}" (${m[1]}) is not ${what} in the chain database yet. Check the number, or make sure its owner has added it.`;
  }
  m = /violates check constraint "(\w+)"/.exec(e.message);
  if (m) return `a value breaks the rule ${m[1]}. Check numbers are not negative and choices are spelled exactly as in the template.`;
  return e.message;
}

// ---------- write ----------
const client = new pg.Client({ connectionString: DB_URL, ssl: /localhost|127\.0\.0\.1/.test(DB_URL) ? false : { rejectUnauthorized: false } });
await client.connect();
const q = (sql, params) => client.query(sql, params);

async function attempt(team, file, fn) {
  await q('savepoint s');
  try { await fn(); await q('release savepoint s'); return true; }
  catch (e) { await q('rollback to savepoint s'); issue(team, file, plainDbError(e)); return false; }
}

await q('begin');

// Phase 0: teams
for (const t of teams) {
  if (!t.prefix) issue(t.slug, 'assignments.json', 'has no gln_prefix for this team yet (instructor).', 'warning');
  await q(`insert into teams (team, name, link, chain, repo, storefront, gln_prefix, members)
           values ($1,$2,$3,$4,$5,$6,$7,$8)
           on conflict (team) do update set name=$2, link=$3, chain=$4, repo=$5, storefront=$6, gln_prefix=$7, members=$8`,
    [t.slug, t.team, t.link, t.chain, t.repo, t.storefront, t.prefix, t.members || []]);
}

// Clone everything first, so one broken repo does not stop the others.
const repos = [];
for (const t of teams) {
  try { repos.push({ t, dir: cloneTeam(t) }); }
  catch (e) { issue(t.slug, null, `could not read the repo ${t.repo}. Is it public, and is the name in the registry right?`); }
}

const owned = new Map(); // gln -> team, built as parties load
for (const r of (await q('select gln, team from parties')).rows) owned.set(r.gln, r.team);

// Phase 1: domain (parties and products) for every team, before anything references them
for (const { t, dir } of repos) {
  const rel = 'domain.json';
  const d = readJson(t, dir, rel);
  if (d === undefined) { issue(t.slug, rel, 'is missing. Copy team-kit/domain.json into your repo and fill it in.'); continue; }
  if (!d) continue;
  for (const [i, p] of (d.parties || []).entries()) {
    const at = `${rel} parties[${i}]`;
    const gln = str(p.gln);
    if (!gln || !GLN.test(gln)) { issue(t.slug, at, `gln "${p.gln ?? ''}" must be exactly 13 digits.`); continue; }
    if (t.prefix && !gln.startsWith(t.prefix)) { issue(t.slug, at, `gln ${gln} must start with your team prefix ${t.prefix}.`); continue; }
    if (owned.has(gln) && owned.get(gln) !== t.slug) { issue(t.slug, at, `gln ${gln} already belongs to ${owned.get(gln)}.`); continue; }
    if (!str(p.name) || !str(p.role)) { issue(t.slug, at, 'needs a "name" and a "role" (e.g. farm, elevator, processor, carrier, store).'); continue; }
    if (dryRun) { bump(t.slug, 'parties'); continue; }
    if (await attempt(t.slug, at, () => q(
      `insert into parties (gln, name, role, county, city, team) values ($1,$2,$3,$4,$5,$6)
       on conflict (gln) do update set name=$2, role=$3, county=$4, city=$5, team=$6`,
      [gln, str(p.name), str(p.role), str(p.county), str(p.city), t.slug]))) { owned.set(gln, t.slug); bump(t.slug, 'parties'); }
  }
  for (const [i, p] of (d.products || []).entries()) {
    const at = `${rel} products[${i}]`;
    const gtin = str(p.gtin);
    if (!gtin || !GTIN.test(gtin)) { issue(t.slug, at, `gtin "${p.gtin ?? ''}" must be exactly 14 digits.`); continue; }
    if (t.prefix && !gtin.startsWith(t.prefix)) { issue(t.slug, at, `gtin ${gtin} must start with your team prefix ${t.prefix}.`); continue; }
    if (!str(p.name) || !str(p.uom)) { issue(t.slug, at, 'needs a "name" and a "uom" (unit: bu, cwt, lb, ton, each, head).'); continue; }
    const prev = (await q('select team from products where gtin=$1', [gtin])).rows[0];
    if (prev && prev.team && prev.team !== t.slug) { issue(t.slug, at, `gtin ${gtin} already belongs to ${prev.team}.`); continue; }
    if (dryRun) { bump(t.slug, 'products'); continue; }
    if (await attempt(t.slug, at, () => q(
      `insert into products (gtin, name, uom, grade, description, team) values ($1,$2,$3,$4,$5,$6)
       on conflict (gtin) do update set name=$2, uom=$3, grade=$4, description=$5, team=$6`,
      [gtin, str(p.name), str(p.uom), str(p.grade), str(p.description), t.slug]))) bump(t.slug, 'products');
  }
}

// Phase 2: capabilities and metric definitions (the repo file is the whole truth: removed items are removed)
for (const { t, dir } of repos) {
  const members = (t.members || []).map(m => m.toLowerCase());
  const caps = collect(t, dir, 'capabilities.json', 'capabilities', 'capabilities');
  if (!caps.found) issue(t.slug, 'capabilities/', 'no capabilities yet. Each teammate adds one file to capabilities/ (copy team-kit/capabilities/_capability.json).', 'warning');
  if (caps.found) {
    const keep = [];
    for (const { at, item: c } of caps.items) {
      const id = str(c.id);
      if (!id || !ID.test(id)) { issue(t.slug, at, `"id" must be lowercase words joined by dashes, e.g. "receive-corn".`); continue; }
      if (!SCOR.includes(str(c.scor_process)?.toLowerCase())) { issue(t.slug, at, `"scor_process" must be one of: ${SCOR.join(', ')}.`); continue; }
      if (!str(c.name)) { issue(t.slug, at, 'needs a "name".'); continue; }
      if (c.capacity_period && !PERIODS.includes(c.capacity_period)) { issue(t.slug, at, `"capacity_period" must be one of: ${PERIODS.join(', ')}.`); continue; }
      if (c.site_gln && owned.get(str(c.site_gln)) !== t.slug) { issue(t.slug, at, `"site_gln" ${c.site_gln} is not one of your parties in domain.json.`); continue; }
      if (!str(c.owner)) issue(t.slug, at, 'has no "owner". Put the GitHub username of the teammate responsible.', 'warning');
      else if (!members.includes(str(c.owner).toLowerCase())) issue(t.slug, at, `"owner" ${c.owner} is not a member of this team in the registry.`, 'warning');
      const key = `${t.slug}/${id}`;
      keep.push(key);
      if (dryRun) { bump(t.slug, 'capabilities'); continue; }
      if (await attempt(t.slug, at, () => q(
        `insert into capabilities (capability_key, team, scor_process, name, description, gtin, party_gln,
           capacity_qty, capacity_uom, capacity_period, lead_time_days, quality_promise, price, price_uom, owner_github, evidence)
         values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
         on conflict (capability_key) do update set scor_process=$3, name=$4, description=$5, gtin=$6, party_gln=$7,
           capacity_qty=$8, capacity_uom=$9, capacity_period=$10, lead_time_days=$11, quality_promise=$12,
           price=$13, price_uom=$14, owner_github=$15, evidence=$16`,
        [key, t.slug, c.scor_process.toLowerCase(), str(c.name), str(c.description), str(c.product_gtin), str(c.site_gln),
         num(c.capacity_qty), str(c.capacity_uom), str(c.capacity_period), num(c.lead_time_days), str(c.quality_promise),
         num(c.price), str(c.price_uom), str(c.owner), str(c.evidence)]))) bump(t.slug, 'capabilities');
    }
    if (!dryRun && !caps.broken) await q('delete from capabilities where team=$1 and not (capability_key = any($2))', [t.slug, keep]);
  }

  const mets = collect(t, dir, 'metrics.json', 'metrics', 'metrics');
  if (mets.found) {
    const keep = [];
    for (const { at, item: m } of mets.items) {
      const id = str(m.id);
      if (!id || !ID.test(id)) { issue(t.slug, at, `"id" must be lowercase words joined by dashes, e.g. "on-time-ship".`); continue; }
      if (!str(m.name) || !str(m.definition)) { issue(t.slug, at, 'needs a "name" and a "definition".'); continue; }
      if (m.scor_attribute && !ATTRS.includes(m.scor_attribute)) { issue(t.slug, at, `"scor_attribute" must be one of: ${ATTRS.join(', ')}.`); continue; }
      const key = `${t.slug}/${id}`;
      keep.push(key);
      if (dryRun) { bump(t.slug, 'metrics'); continue; }
      if (await attempt(t.slug, at, () => q(
        `insert into metric_definitions (metric_key, team, name, scor_attribute, definition, calculation, data_needed, target, unit, owner_github)
         values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
         on conflict (metric_key) do update set name=$3, scor_attribute=$4, definition=$5, calculation=$6,
           data_needed=$7, target=$8, unit=$9, owner_github=$10`,
        [key, t.slug, str(m.name), str(m.scor_attribute), str(m.definition), str(m.calculation), str(m.data_needed),
         num(m.target), str(m.unit), str(m.owner)]))) bump(t.slug, 'metrics');
    }
    if (!dryRun && !mets.broken) await q('delete from metric_definitions where team=$1 and not (metric_key = any($2))', [t.slug, keep]);
  }
}

// Phase 3: signals, oldest first across all teams (an acknowledgement can answer an order synced in the same run)
const known = new Map((await q('select signal_key, signal_type, from_gln, to_gln, gtin, quantity, need_by::text, promised_on::text, responds_to from signals')).rows.map(r => [r.signal_key, r]));
const pendingSignals = [];
for (const { t, dir } of repos) {
  for (const rel of listJsonFiles(dir, 'signals')) {
    const s = readJson(t, dir, rel);
    if (!s) continue;
    const key = `${t.slug}/${path.basename(rel, '.json')}`;
    const commit = await firstCommit(t, dir, rel);
    pendingSignals.push({ t, rel, s, key, commit });
  }
}
pendingSignals.sort((a, b) => a.commit.at.localeCompare(b.commit.at));
for (const { t, rel, s, key, commit } of pendingSignals) {
  const type = str(s.type);
  const row = {
    type, from: str(s.from_gln), to: str(s.to_gln), gtin: str(s.gtin), qty: num(s.quantity), uom: str(s.uom),
    need_by: str(s.need_by), promised_on: str(s.promised_on), responds_to: str(s.responds_to),
  };
  if (known.has(key)) {
    const k = known.get(key);
    const same = k.signal_type === row.type && k.from_gln === row.from && k.to_gln === row.to && (k.gtin ?? null) === row.gtin
      && (k.quantity === null ? row.qty === null : Number(k.quantity) === row.qty) && (k.need_by ?? null) === row.need_by
      && (k.promised_on ?? null) === row.promised_on && (k.responds_to ?? null) === row.responds_to;
    if (!same) issue(t.slug, rel, 'was already sent, so edits to it are ignored. A signal is permanent: send a new signal that corrects it.', 'warning');
    continue;
  }
  if (!SIGNAL_TYPES.includes(type)) { issue(t.slug, rel, `"type" must be one of: ${SIGNAL_TYPES.join(', ')}.`); continue; }
  if (!row.from || owned.get(row.from) !== t.slug) { issue(t.slug, rel, `"from_gln" ${row.from ?? '(blank)'} must be one of YOUR parties. You can only send signals as yourself.`); continue; }
  if (!row.to || !owned.has(row.to)) { issue(t.slug, rel, `"to_gln" ${row.to ?? '(blank)'} is not a party in the chain database. Check the chain page for the right number.`); continue; }
  if (row.need_by && !DATE.test(row.need_by)) { issue(t.slug, rel, '"need_by" must be a date like 2026-11-24.'); continue; }
  if (row.promised_on && !DATE.test(row.promised_on)) { issue(t.slug, rel, '"promised_on" must be a date like 2026-11-24.'); continue; }
  if (type === 'order' && (!row.gtin || !row.qty || !row.uom || !row.need_by)) { issue(t.slug, rel, 'an order needs "gtin", "quantity", "uom" and "need_by".'); continue; }
  if (type === 'acknowledgement') {
    if (!row.responds_to) { issue(t.slug, rel, 'an acknowledgement needs "responds_to": the signal key of the order it answers (shown on the chain page).'); continue; }
    const o = known.get(row.responds_to);
    if (!o) { issue(t.slug, rel, `"responds_to" ${row.responds_to} is not a signal in the chain database yet.`); continue; }
    if (o.to_gln !== row.from) { issue(t.slug, rel, `order ${row.responds_to} was sent to ${o.to_gln}, so only that party can acknowledge it.`); continue; }
    if (!row.promised_on) { issue(t.slug, rel, 'an acknowledgement needs "promised_on": the date you promise to deliver.'); continue; }
  }
  if (!commit.by || !(t.members || []).map(m => m.toLowerCase()).includes(String(commit.by).toLowerCase()))
    issue(t.slug, rel, `was committed by ${commit.by ?? 'an unknown author'}, who is not listed as a member of this team.`, 'warning');
  if (dryRun) { bump(t.slug, 'signals'); continue; }
  if (await attempt(t.slug, rel, () => q(
    `insert into signals (signal_key, signal_type, from_gln, to_gln, gtin, quantity, uom, need_by, promised_on, responds_to, note, sent_at, sent_by_team, sent_by_github)
     values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)`,
    [key, type, row.from, row.to, row.gtin, row.qty, row.uom, row.need_by, row.promised_on, row.responds_to, str(s.note), commit.at, t.slug, commit.by]))) {
    known.set(key, { signal_key: key, signal_type: type, from_gln: row.from, to_gln: row.to, gtin: row.gtin, quantity: row.qty, need_by: row.need_by, promised_on: row.promised_on, responds_to: row.responds_to });
    bump(t.slug, 'signals');
  }
}

// Phase 4: events (physical flow)
const knownEvents = new Set((await q('select event_key from events where event_key is not null')).rows.map(r => r.event_key));
const pendingEvents = [];
for (const { t, dir } of repos) {
  for (const rel of listJsonFiles(dir, 'events')) {
    const e = readJson(t, dir, rel);
    if (!e) continue;
    const key = `${t.slug}/${path.basename(rel, '.json')}`;
    if (knownEvents.has(key)) continue; // permanent once recorded
    pendingEvents.push({ t, rel, e, key, commit: await firstCommit(t, dir, rel) });
  }
}
pendingEvents.sort((a, b) => a.commit.at.localeCompare(b.commit.at) || String(a.e.occurred_at || '').localeCompare(String(b.e.occurred_at || '')));
const CREATES_LOT = ['harvest', 'initial_packing', 'transformation'];
for (const { t, rel, e, key, commit } of pendingEvents) {
  const type = str(e.type);
  const from = str(e.from_gln), to = str(e.to_gln), lot = str(e.lot_code), gtin = str(e.gtin);
  if (!EVENT_TYPES.includes(type)) { issue(t.slug, rel, `"type" must be one of: ${EVENT_TYPES.join(', ')}.`); continue; }
  const mine = gln => gln && owned.get(gln) === t.slug;
  if (type === 'shipping' && !mine(from)) { issue(t.slug, rel, 'a shipping event must ship FROM one of your parties.'); continue; }
  if (type === 'receiving' && !mine(to)) { issue(t.slug, rel, 'a receiving event must be received AT one of your parties.'); continue; }
  if (!['shipping', 'receiving'].includes(type) && !mine(from) && !mine(to)) { issue(t.slug, rel, 'this event must happen at one of your parties (from_gln or to_gln).'); continue; }
  if (!gtin || !num(e.quantity) || !str(e.uom)) { issue(t.slug, rel, 'needs "gtin", "quantity" and "uom".'); continue; }
  if (e.occurred_at && isNaN(Date.parse(e.occurred_at))) { issue(t.slug, rel, '"occurred_at" must look like 2026-11-19T10:30:00-06:00.'); continue; }
  if (e.order_key && !known.has(str(e.order_key))) { issue(t.slug, rel, `"order_key" ${e.order_key} is not an order in the chain database.`); continue; }
  if (dryRun) { bump(t.slug, 'events'); continue; }
  await attempt(t.slug, rel, async () => {
    if (lot && CREATES_LOT.includes(type)) {
      await q(`insert into lots (lot_code, gtin, origin_gln, created_on) values ($1,$2,$3,$4::date) on conflict (lot_code) do nothing`,
        [lot, gtin, to || from, (e.occurred_at || commit.at).slice(0, 10)]);
    }
    await q(`insert into events (event_key, event_type, gtin, lot_code, input_lot_code, quantity, uom, from_gln, to_gln, occurred_at,
               recorded_by_team, order_key, recorded_by_github, committed_at)
             values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)`,
      [key, type, gtin, lot, str(e.input_lot_code), num(e.quantity), str(e.uom), from, to, e.occurred_at || commit.at,
       t.slug, str(e.order_key), commit.by, commit.at]);
  }) && bump(t.slug, 'events');
}

// Record what happened
const synced = teams.map(t => t.slug);
await q('delete from sync_issues where team = any($1)', [synced]);
for (const i of issues) await q('insert into sync_issues (team, file, message, level) values ($1,$2,$3,$4)', [i.team, i.file, i.message, i.level]);
await q('insert into sync_runs (summary) values ($1)', [JSON.stringify({ dryRun, teams: synced.length, count, issues: issues.length })]);
if (dryRun) await q('rollback'); else await q('commit');
await client.end();
fs.rmSync(work, { recursive: true, force: true });

// Report for the Actions log
for (const t of teams) {
  const c = count[t.slug] || {};
  const mine = issues.filter(i => i.team === t.slug);
  console.log(`\n${mine.some(i => i.level === 'error') ? '✗' : '✓'} ${t.team}  ` +
    Object.entries(c).map(([k, v]) => `${v} ${k}`).join(', '));
  for (const i of mine) console.log(`    ${i.level === 'error' ? '✗' : '!'} ${i.file ?? ''}: ${i.message}`);
}
console.log(`\n${dryRun ? 'Dry run, nothing saved.' : 'Saved.'} ${issues.length} issue(s).`);
