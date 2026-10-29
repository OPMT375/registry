// Builds the published directory: _site/index.html + _site/registry.json from teams/*.json.
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
fs.copyFileSync(path.join(root, 'site', 'index.html'), path.join(out, 'index.html'));
console.log(`Built directory with ${teams.length} team(s).`);
