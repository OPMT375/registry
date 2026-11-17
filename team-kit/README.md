# Team kit: putting your firm in the chain database

Your repo is your firm's system of record. If something isn't in the repo, it didn't happen.

The class sync reads the files below and copies them into one shared chain database, which every firm can see on the **chain page**. You never log in to the database. You commit files, and the commit records who did it and when.

## Step 1 · Master data: `domain.json` (Tuesday)

Copy `domain.json` from this kit into the top level of your repo. Fill it in with:

- **parties:** every place your firm operates, such as an elevator, plant, truck yard or store. Each party gets a **GLN**, a 13-digit location number.
- **products:** every kind of thing you handle or sell. Each product gets a **GTIN**, a 14-digit item number.

Every GLN and GTIN must **start with your team prefix**, which is on the chain page and in `assignments.json`. After the prefix, number them yourselves (`…000001`, `…000002`). The sync rejects any code that starts with another team's prefix: you can't name someone else's things.

## Step 2 · Capabilities: `capabilities/` (Tuesday)

Write one file for each thing your firm can promise a customer. **Each teammate owns at least one capability and commits it themselves**, so your name is on it:

1. Copy `capabilities/_capability.json` into your repo as `capabilities/<id>.json`, for example `capabilities/receive-corn.json`. The file name is the capability's id.
2. Put your GitHub username in `owner`.

| Field | What to write |
|---|---|
| (file name) | short name, lowercase with dashes: `receive-corn.json` |
| `scor_process` | `plan`, `source`, `make`, `deliver`, `return` or `enable` |
| `name`, `description` | what you do, in words a customer understands |
| `product_gtin`, `site_gln` | which of your products and parties this uses |
| `capacity_qty`, `capacity_uom`, `capacity_period` | how much you can do, per `hour`, `day`, `week` or `month` |
| `lead_time_days` | how long from order to ready |
| `quality_promise` | what you guarantee, and how you check it |
| `price`, `price_uom` | what you charge, and per what |
| `owner` | the teammate responsible |
| `evidence` | a link showing a real firm does this at about this scale |

## Step 3 · Signals: `signals/` (Thursday on)

Each signal is one file, and its file name becomes its key. The templates start with `_`, which the sync ignores.

1. Copy the template you need into `signals/` with a new name, for example `signals/2026-11-19-po-001.json`.
2. Fill it in and commit. The commit time is the time the signal was sent.

| Template | Use it to |
|---|---|
| `_order.json` | ask a supplier for product by a date |
| `_acknowledgement.json` | answer an order you received with a promise date (`responds_to` = the order key from the chain page) |
| `_forecast.json` | tell a supplier what you expect to order |
| `_alert.json` | warn a partner about a delay, quality problem or capacity change |

**Signals are permanent.** If you got one wrong, send a new signal that corrects it. Edits to a signal that has already been sent are ignored.

## Step 4 · Events: `events/` (Thursday on)

Physical flow works the same way: one file per event. Use these templates:

- `_harvest.json` creates a lot.
- `_shipping.json` records goods leaving one of your parties. Set `order_key` to the order it fills.
- `_receiving.json` records goods arriving at one of your parties.

## Step 5 · Metrics: `metrics/` (Thursday)

Copy `metrics/_metric.json` into your repo as `metrics/<id>.json`. Whoever owns the metric writes a definition precise enough that a stranger would count exactly what you count.

## When something is wrong

The chain page's **Sync check** lists every file the sync couldn't accept, with the reason. Fix the file, commit, and the issue clears on the next sync.
