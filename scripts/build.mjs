// Builds the published directory: _site/index.html, chain.html, config.js + _site/registry.json from teams/*.json.
import fs from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const out = path.join(root, '_site');
fs.mkdirSync(out, { recursive: true });

const teamsDir = path.join(root, 'teams');
const teams = (fs.existsSync(teamsDir) ? fs.readdirSync(teamsDir) : [])
  .filter(f => f.endsWith('.json'))
  .map(f => ({ id: f.replace(/\.json$/, ''), ...JSON.parse(fs.readFileSync(path.join(teamsDir, f), 'utf8')) }))
  .sort((a, b) => String(a.chain).localeCompare(String(b.chain)) || String(a.team).localeCompare(String(b.team)));

fs.writeFileSync(path.join(out, 'registry.json'), JSON.stringify({ updated: new Date().toISOString(), teams }, null, 2));
for (const f of ['index.html', 'chain.html', 'config.js']) fs.copyFileSync(path.join(root, 'site', f), path.join(out, f));
console.log(`Built directory with ${teams.length} team(s).`);
