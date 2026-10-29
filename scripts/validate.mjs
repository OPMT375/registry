// Validates team entries in teams/*.json against the schema and the instructor's assignments.
// Usage: node scripts/validate.mjs [--author <github-login>] [--changed teams/a.json,teams/b.json]
// No dependencies; runs on the GitHub Actions default Node.
import fs from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const args = process.argv.slice(2);
const arg = k => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const author = (arg('--author') || '').toLowerCase();
const changed = (arg('--changed') || '').split(',').map(s => s.trim()).filter(s => s.startsWith('teams/') && s.endsWith('.json'));

const errors = [];
const fail = (file, msg) => errors.push(`${file}: ${msg}`);

const assignments = JSON.parse(fs.readFileSync(path.join(root, 'assignments.json'), 'utf8'));
const LINKS = assignments.allowed_links;
const teamsDir = path.join(root, 'teams');
const files = fs.existsSync(teamsDir) ? fs.readdirSync(teamsDir).filter(f => f.endsWith('.json')) : [];

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const GH_USER = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/;
const REPO = /^[A-Za-z0-9-]+\/[A-Za-z0-9._-]+$/;
const names = new Map();

for (const f of files) {
  const rel = `teams/${f}`;
  const slug = f.replace(/\.json$/, '');
  let t;
  try { t = JSON.parse(fs.readFileSync(path.join(teamsDir, f), 'utf8')); }
  catch (e) { fail(rel, `not valid JSON (${e.message})`); continue; }

  if (!SLUG.test(slug)) fail(rel, 'file name must be lowercase letters, digits and dashes, e.g. teams/brick-house.json');
  for (const k of ['team', 'link', 'chain', 'repo', 'storefront', 'members']) if (t[k] === undefined || t[k] === '') fail(rel, `missing "${k}"`);

  if (t.team) {
    const key = String(t.team).trim().toLowerCase();
    if (names.has(key)) fail(rel, `team name "${t.team}" is already used by ${names.get(key)}`);
    names.set(key, rel);
  }
  if (t.link && !LINKS.includes(t.link)) fail(rel, `"link" must be one of: ${LINKS.join(', ')}`);
  if (t.repo && !REPO.test(t.repo)) fail(rel, '"repo" must look like owner/repo-name');
  if (t.storefront) {
    let u = null; try { u = new URL(t.storefront); } catch {}
    if (!u || u.protocol !== 'https:' || !u.hostname.endsWith('.github.io')) fail(rel, '"storefront" must be your https://<owner>.github.io/<repo>/ address');
    else if (t.repo) {
      const [owner, name] = t.repo.split('/');
      if (u.hostname.toLowerCase() !== `${owner.toLowerCase()}.github.io`) fail(rel, `"storefront" host should be ${owner.toLowerCase()}.github.io to match "repo"`);
      const first = u.pathname.split('/').filter(Boolean)[0] || '';
      if (first.toLowerCase() !== name.toLowerCase() && name.toLowerCase() !== `${owner.toLowerCase()}.github.io`) fail(rel, `"storefront" path should be /${name}/ to match "repo"`);
    }
  }
  if (t.members !== undefined) {
    if (!Array.isArray(t.members) || t.members.length === 0) fail(rel, '"members" must list at least one GitHub username');
    else for (const m of t.members) if (typeof m !== 'string' || !GH_USER.test(m)) fail(rel, `"${m}" is not a valid GitHub username (list usernames as strings)`);
  }

  // The instructor assigns links; a team cannot pick its own.
  const a = assignments.teams[slug];
  if (!a) fail(rel, `no assignment for "${slug}" yet. Ask the instructor to add it to assignments.json, using this exact file name.`);
  else {
    if (t.link && t.link !== a.link) fail(rel, `assigned link is "${a.link}", not "${t.link}"`);
    if (t.chain && t.chain !== a.chain) fail(rel, `assigned chain is "${a.chain}", not "${t.chain}"`);
  }

  // Identity: the person opening the PR must be on the team they are editing.
  if (author && changed.includes(rel) && Array.isArray(t.members) &&
      !t.members.map(m => String(m).toLowerCase()).includes(author)) {
    fail(rel, `@${author} is not listed in "members", so you can only edit your own team's entry`);
  }
}

if (errors.length) {
  console.log('Registry check failed:\n');
  for (const e of errors) console.log('  ✗ ' + e);
  process.exit(1);
}
console.log(`Registry check passed (${files.length} team${files.length === 1 ? '' : 's'}).`);
