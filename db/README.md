# Chain database: instructor setup

One Supabase project holds the whole chain. Teams never touch it. Each team's repo is its own system of record, and the sync copies what they commit into this database. The database is the consolidated view, like the analytics copy that sits outside the ERPs in the Nov 12 lecture.

```
team repos (domain.json, capabilities/, metrics/, signals/, events/)
        │  git commit = the record, with author and time
        ▼
scripts/sync.mjs  ── validates, enforces identity, writes ──►  Supabase (db/chain.sql)
        ▲                                                         │ read-only, public key
your demand code ── inserts consumer orders directly ─────────────┘
                                                                  ▼
                                                     site/chain.html (the chain page)
```

## One-time setup (about 15 minutes)

1. **Create the project.** Go to supabase.com and create a new project, for example `opmt375-chain`. Save the database password.
2. **Create the tables.** Open SQL Editor → New query, paste all of `db/chain.sql`, and click Run. It is safe to run again later.
3. **Give the sync its connection string.**
   - In Supabase, click **Connect** at the top, then copy the **Session pooler** URI and put your password in it.
   - Use the pooler, not the "Direct connection". The direct host is IPv6-only, and GitHub's runners can't reach it.
   - In this repo, go to **Settings → Secrets and variables → Actions → New repository secret**. Name it `SUPABASE_DB_URL` and paste the URI.
4. **Connect the chain page.** In Supabase, go to Project Settings → API. Copy the Project URL and the **anon** key into `site/config.js`, then commit.
   - The anon key is public by design: the database only allows reads with it.
   - Never put the `service_role` key or the database password in the repo.
5. **Assign prefixes.** In `assignments.json`, give every team a `gln_prefix`: `0999` plus a two-digit team number (`099901`, `099902`, …). `099900` is reserved for the consumer and the samples.
6. **Run it.** Go to Actions → **Sync chain database** → Run workflow. After that it also runs every 10 minutes. The chain page is published at `<pages-url>/chain.html`.

### Running the sync from your laptop during class

Running it locally is faster than waiting for the Actions queue:

```bash
npm install
SUPABASE_DB_URL='postgresql://...pooler.supabase.com:5432/postgres' GITHUB_TOKEN=$(gh auth token) node scripts/sync.mjs
```

`--team <slug>` syncs a single team, and `--dry-run` checks everything without saving.

## What the sync enforces

| Rule | What students see on the chain page if they break it |
|---|---|
| A team's GLNs and GTINs start with its prefix | `gln … must start with your team prefix 099904` |
| A team can only send signals from its own parties | `You can only send signals as yourself` |
| Only the party an order was sent to can acknowledge it | `order … was sent to …, so only that party can acknowledge it` |
| Shipping goes out from your party, and receiving comes in at it | `a shipping event must ship FROM one of your parties` |
| Signals and events are permanent once synced | `already sent, so edits to it are ignored` (a warning) |
| A signal's `sent_at` is the file's first commit time | (not typed by students, so it can't be backdated) |
| A commit should come from a listed team member | a warning naming the committer |

`domain.json`, `capabilities/` and `metrics/` are master data. The repo is the truth: edit a file, and the next sync updates the row. A capability or metric whose file is deleted is removed from the database, unless some file in that folder is broken JSON, in which case nothing is removed that run. A single `capabilities.json` or `metrics.json` holding a list also works. Parties and products are never deleted, because events point at them.

## Your demand code: the contract

Consumer orders go straight into `signals`. Use the service key or the database URL, never the anon key.

```sql
insert into signals (signal_key, signal_type, from_gln, to_gln, gtin, quantity, uom, need_by, note, sent_by_team)
values ('consumer/2026-11-19-001',  -- unique; teams paste this into responds_to and order_key
        'order',
        '0999000000900',            -- The Hungry Consumers (created by chain.sql)
        '<Sell team store GLN>',    -- from the Codes table on the chain page
        '<Sell team product GTIN>',
        120, 'each', '2026-11-23',
        'Thanksgiving week',
        'consumer');
-- sent_at defaults to now(). Set it explicitly to backfill history.
```

Notes on the rest of the contract:

- **Other signal types:** a `forecast` with the same columns, or an `alert` that needs only `note`, can go to any party. Use them to hint at the launch.
- **What teams send back:** an `acknowledgement` with `responds_to = 'consumer/…'` and a `promised_on` date. Then a `shipping` event to `0999000000900` with `order_key = 'consumer/…'` closes the order on the board.
- **Useful views:**
  - `v_orders`: status and minutes to acknowledge for every order.
  - `v_team_signals`: answer speed by firm.
  - `v_capability_map`: every firm's capabilities.
  - `v_contributions`: per-student counts.

## Tested

This was run against PostgreSQL 16 in this order: the v1 `spine.sql`, then `chain.sql` twice. The sync was then run over two fake team repos. The test covered:

- valid domain, capabilities, metrics, signals and events
- a wrong prefix
- broken JSON
- a forged `from_gln`
- an edit to a signal that had already been sent
- a dry run
- reads with the anon role

Every case produced the expected rows or the expected message.
