# Final project starter kit

Files for **Make the Case to Switch Suppliers**. Copy them into **your team's storefront repo**, not into this registry.

| File in this kit | Where it goes in your team repo | Who adds it | When |
|---|---|---|---|
| [`dashboard/metrics.csv`](dashboard/metrics.csv) | `dashboard/metrics.csv` | One teammate (the header row only) | Before Checkpoint A, Mon Nov 30 |
| [`dashboard/index.html`](dashboard/index.html) | `dashboard/index.html` | One teammate | Before Checkpoint B, Wed Dec 2 |
| [`students/_template/index.html`](students/_template/index.html) | `students/your-name/index.html` | **Each of you** | Before Checkpoint C, Wed Dec 9 |
| [`students/_template/ai-log.md`](students/_template/ai-log.md) | `students/your-name/ai-log.md` | **Each of you** | Now, and keep it current |
| [`pitch/README.md`](pitch/README.md) | `pitch/README.md` | One teammate | Before rehearsal, Tue Dec 15 |

If your team already has a working dashboard that reads `metrics.csv` with these columns, keep it. You do not need this one.

## How to copy a file (in the browser, no installs)

1. Open the file in this kit on GitHub and click **Raw**. Select everything and copy it.
2. In **your team repo**, click **Add file → Create new file**.
3. In the name box, type the full path, for example `dashboard/metrics.csv`. Typing the `/` creates the folder.
4. Paste, then **Commit changes**. If you are adding your own folder, choose **Create a new branch** and open a pull request so a teammate reviews it.

## metrics.csv: one row each

The header is:

```
pillar,owner,metric,unit,incumbent_value,our_value,target,real_company,source_url,as_of
```

Add **only your own row**, through your own pull request, so your commits show your work. Example:

```
DELIVER,Pat L.,Order fulfillment cycle time,days,6,2.5,3,Land O'Lakes,https://example.org/source,2025-06-01
```

- Put numbers in `incumbent_value`, `our_value` and `target` with no units (the unit goes in `unit`).
- If a value contains a comma, wrap it in double quotes.
- A vendor's own number counts only if you say so: add "(vendor claim)" after the company name.

## Folder rules (we grade by folder)

- There is **one** folder for individual work: `students/` (lowercase).
- Name your folder with lowercase letters and dashes, no spaces: `students/pat-lee/`.
- Your folder holds your data page, your capability page (`index.html`), and `ai-log.md`.
- **To rename a file or move it into a folder:** open it, click the pencil, and edit the name box at the top. Typing `students/pat-lee/` in front of the name moves the file there. Then commit.
- Delete stray empty files (for example a file named after a person instead of a folder).

## Your page addresses

Once GitHub Pages is on, your team's sites are at:

- Home: `https://<owner>.github.io/<repo>/`
- Dashboard: `https://<owner>.github.io/<repo>/dashboard/`
- Your capability page: `https://<owner>.github.io/<repo>/students/your-name/`

The [Supply Lab Directory](https://opmt375.github.io/registry/) checks every team's dashboard and student folders automatically, so you can see what is live.
