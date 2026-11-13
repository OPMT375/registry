-- OPMT 375 Supply Lab: the shared chain database (spine v2)
--
-- Run once in the CLASS Supabase project (instructor only):
--   SQL Editor → New query → paste this whole file → Run. Safe to run again.
--
-- Teams never write here directly. Each team's repo is its own system of record.
-- The sync (scripts/sync.mjs) copies what teams commit into this database, so the
-- database is the consolidated view of the whole chain, the "copy outside the ERP".
--
--   teams              one row per firm (from the registry) plus 'consumer' and 'sample'
--   parties            who and where, named by a GLN        ← domain.json
--   products           what kind of thing, named by a GTIN  ← domain.json
--   lots               one batch of a product               ← created by events
--   capabilities       what a firm can promise              ← capabilities.json
--   signals            orders, acknowledgements, forecasts, alerts   ← signals/*.json
--   events             what physically happened (FSMA 204 critical tracking events) ← events/*.json
--   metric_definitions how a firm says it will measure itself      ← metrics.json
--   sync_issues        what the last sync could not accept, per team
--
-- All codes are FAKE, for class use only. Every GLN and GTIN uses the class prefix 0999.

-- 0. Teams --------------------------------------------------------------------
create table if not exists teams (
  team        text primary key,                       -- registry slug, e.g. minnesota-corn-soybean-storage
  name        text not null,
  link        text,                                    -- Source, Make, Deliver, Sell, ...
  chain       text,
  repo        text,
  storefront  text,
  gln_prefix  text,                                    -- e.g. 099901; every GLN/GTIN this team creates starts with it
  members     text[] not null default '{}'
);

-- 1-4. The v1 spine (unchanged columns; created here if this is a fresh project) ---
create table if not exists parties (
  gln         text primary key check (gln ~ '^[0-9]{13}$'),
  name        text not null,
  role        text not null,
  county      text,
  team        text
);

create table if not exists products (
  gtin        text primary key check (gtin ~ '^[0-9]{14}$'),
  name        text not null,
  uom         text not null,
  grade       text
);

create table if not exists lots (
  lot_code    text primary key,
  gtin        text not null references products (gtin),
  origin_gln  text not null references parties (gln),
  created_on  date not null default current_date
);

create table if not exists events (
  event_id          bigint generated always as identity primary key,
  event_type        text not null check (event_type in
                      ('harvest', 'cooling', 'initial_packing', 'shipping', 'receiving', 'transformation')),
  gtin              text not null references products (gtin),
  lot_code          text references lots (lot_code),
  input_lot_code    text references lots (lot_code),
  quantity          numeric not null check (quantity > 0),
  uom               text not null,
  from_gln          text references parties (gln),
  to_gln            text references parties (gln),
  occurred_at       timestamptz not null default now(),
  recorded_by_team  text not null
);

-- v2 additions to the spine
alter table products add column if not exists team text;
alter table products add column if not exists description text;
alter table parties  add column if not exists city text;
alter table events   add column if not exists event_key text unique;          -- <team>/<file name>; makes the sync idempotent
alter table events   add column if not exists order_key text;                 -- the order signal this shipment fills
alter table events   add column if not exists recorded_by_github text;        -- who committed the file
alter table events   add column if not exists committed_at timestamptz;       -- when it reached the repo
create index if not exists events_lot_idx on events (lot_code);
create index if not exists events_order_idx on events (order_key);

-- 5. Capabilities: what a firm can promise -----------------------------------
create table if not exists capabilities (
  capability_key   text primary key,                    -- <team>/<id>
  team             text not null references teams (team),
  scor_process     text not null check (scor_process in ('plan', 'source', 'make', 'deliver', 'return', 'enable')),
  name             text not null,
  description      text,
  gtin             text references products (gtin),     -- the product this capability handles, if one
  party_gln        text references parties (gln),       -- the site that performs it
  capacity_qty     numeric check (capacity_qty >= 0),
  capacity_uom     text,
  capacity_period  text check (capacity_period in ('hour', 'day', 'week', 'month')),
  lead_time_days   numeric check (lead_time_days >= 0),
  quality_promise  text,
  price            numeric check (price >= 0),
  price_uom        text,
  owner_github     text,                                 -- the student who owns this capability
  evidence         text                                  -- a source that shows a real firm can do this
);

-- 6. Signals: information flow ------------------------------------------------
create table if not exists signals (
  signal_id        bigint generated always as identity primary key,
  signal_key       text not null unique,                 -- <team>/<file name>, or consumer/<id>
  signal_type      text not null check (signal_type in ('order', 'acknowledgement', 'forecast', 'alert')),
  from_gln         text not null references parties (gln),
  to_gln           text not null references parties (gln),
  gtin             text references products (gtin),
  quantity         numeric check (quantity >= 0),
  uom              text,
  need_by          date,                                 -- order: when the buyer needs it
  promised_on      date,                                 -- acknowledgement: when the seller promises it
  responds_to      text references signals (signal_key), -- acknowledgement → the order it answers
  note             text,
  sent_at          timestamptz not null default now(),   -- first commit time of the file (or insert time for the consumer)
  sent_by_team     text not null references teams (team),
  sent_by_github   text
);
create index if not exists signals_to_idx on signals (to_gln, sent_at);
create index if not exists signals_responds_idx on signals (responds_to);

-- 7. Metric definitions -------------------------------------------------------
create table if not exists metric_definitions (
  metric_key      text primary key,                      -- <team>/<id>
  team            text not null references teams (team),
  name            text not null,
  scor_attribute  text check (scor_attribute in ('reliability', 'responsiveness', 'agility', 'cost', 'assets')),
  definition      text not null,                         -- in plain words, what counts and what does not
  calculation     text,                                   -- numerator / denominator, in plain words
  data_needed     text,                                   -- which tables and fields
  target          numeric,
  unit            text,
  owner_github    text
);

-- 8. Sync bookkeeping ---------------------------------------------------------
create table if not exists sync_issues (
  issue_id    bigint generated always as identity primary key,
  team        text not null,
  file        text,
  message     text not null,
  level       text not null default 'error' check (level in ('error', 'warning')),
  found_at    timestamptz not null default now()
);

create table if not exists sync_runs (
  run_id      bigint generated always as identity primary key,
  ran_at      timestamptz not null default now(),
  summary     jsonb
);

-- 9. Views for the chain page (read with the public key) ----------------------
create or replace view v_orders with (security_invoker = true) as
select
  o.signal_key                      as order_key,
  o.sent_by_team                    as buyer_team,
  pt.team                           as seller_team,
  fp.name                           as buyer,
  tp.name                           as seller,
  pr.name                           as product,
  o.quantity, o.uom, o.need_by, o.sent_at, o.note,
  a.sent_at                         as acknowledged_at,
  a.promised_on,
  round(extract(epoch from (a.sent_at - o.sent_at)) / 60.0, 1) as minutes_to_acknowledge,
  coalesce(sh.shipped_qty, 0)       as shipped_qty,
  sh.last_shipped_at,
  case
    when coalesce(sh.shipped_qty, 0) >= o.quantity then 'shipped'
    when sh.shipped_qty > 0 then 'partly shipped'
    when a.signal_key is not null then 'promised'
    else 'waiting'
  end                               as status
from signals o
join parties fp on fp.gln = o.from_gln
join parties tp on tp.gln = o.to_gln
left join teams pt on pt.team = tp.team
left join products pr on pr.gtin = o.gtin
left join lateral (
  select s.signal_key, s.sent_at, s.promised_on
  from signals s
  where s.responds_to = o.signal_key and s.signal_type = 'acknowledgement'
  order by s.sent_at limit 1
) a on true
left join lateral (
  select sum(e.quantity) as shipped_qty, max(e.occurred_at) as last_shipped_at
  from events e where e.order_key = o.signal_key and e.event_type = 'shipping'
) sh on true
where o.signal_type = 'order';

create or replace view v_team_signals with (security_invoker = true) as
select
  t.team, t.name, t.link,
  count(o.order_key)                                        as orders_received,
  count(o.acknowledged_at)                                  as orders_acknowledged,
  count(*) filter (where o.order_key is not null and o.acknowledged_at is null) as orders_waiting,
  percentile_cont(0.5) within group (order by o.minutes_to_acknowledge) as median_minutes_to_acknowledge,
  (select count(*) from signals s where s.sent_by_team = t.team) as signals_sent
from teams t
left join v_orders o on o.seller_team = t.team
where t.team not in ('sample')
group by t.team, t.name, t.link;

create or replace view v_capability_map with (security_invoker = true) as
select
  c.capability_key, c.team, t.name as team_name, t.link, c.scor_process, c.name, c.description,
  pr.name as product, pa.name as site, c.capacity_qty, c.capacity_uom, c.capacity_period,
  c.lead_time_days, c.quality_promise, c.price, c.price_uom, c.owner_github, c.evidence
from capabilities c
join teams t on t.team = c.team
left join products pr on pr.gtin = c.gtin
left join parties pa on pa.gln = c.party_gln;

-- Who moved the chain: one row per person with anything attributed to them.
create or replace view v_contributions with (security_invoker = true) as
with people as (
  select t.team, unnest(t.members) as github from teams t
)
select
  p.team, p.github,
  (select count(*) from signals s where lower(s.sent_by_github) = lower(p.github))            as signals_sent,
  (select count(*) from events e where lower(e.recorded_by_github) = lower(p.github))         as events_recorded,
  (select count(*) from capabilities c where lower(c.owner_github) = lower(p.github))         as capabilities_owned,
  (select count(*) from metric_definitions m where lower(m.owner_github) = lower(p.github))   as metrics_owned,
  greatest(
    (select max(s.sent_at) from signals s where lower(s.sent_by_github) = lower(p.github)),
    (select max(e.committed_at) from events e where lower(e.recorded_by_github) = lower(p.github))
  )                                                                                             as last_active
from people p;

-- 10. Access rules ------------------------------------------------------------
-- The chain page uses the public (anon) key, so anyone may READ.
-- Only the sync, which connects with the database password, may write.
do $$
declare t text;
begin
  foreach t in array array['teams','parties','products','lots','events','capabilities','signals','metric_definitions','sync_issues','sync_runs'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists "public read" on %I', t);
    execute format('create policy "public read" on %I for select using (true)', t);
  end loop;
end $$;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    grant select on teams, parties, products, lots, events, capabilities, signals,
                    metric_definitions, sync_issues, sync_runs,
                    v_orders, v_team_signals, v_capability_map, v_contributions to anon;
  end if;
end $$;

-- 11. Fixed rows: the class teams that are not student firms ------------------
insert into teams (team, name, link, chain, gln_prefix) values
  ('consumer', 'The Hungry Consumers', 'Consumer', null, '099900'),
  ('sample',   'Sample rows',          null,       null, '099900')
on conflict (team) do nothing;

insert into parties (gln, name, role, county, city, team) values
  ('0999000000900', 'The Hungry Consumers', 'consumer', 'Ramsey', 'Saint Paul', 'consumer')
on conflict (gln) do nothing;

-- Sample rows from spine v1 (the turkey chain). Tag them so the chain page can hide them.
update parties  set team = 'sample' where gln  like '09990000000%' and gln <> '0999000000900' and team is distinct from 'consumer';
update products set team = 'sample' where gtin like '09990000000%' and team is null;
