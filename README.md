# Supply Lab registry

This is the class directory of firms. The published directory page lists every registered team by chain, with links to each team's storefront and contact page.

## How your team joins

1. Get your team's slug from the instructor (for example `brick-house`). It must match the name in `assignments.json`.
2. Open this repo on GitHub, go to `teams/`, and choose **Add file → Create new file**.
3. Name the file `teams/<your-slug>.json` and paste in:

```json
{
  "team": "Your Team Name",
  "link": "Source+Make",
  "chain": "A",
  "repo": "owner/your-storefront-repo",
  "storefront": "https://owner.github.io/your-storefront-repo/",
  "members": ["your-username", "teammate-1", "teammate-2", "teammate-3"]
}
```

4. Choose **Propose new file**, then **Create pull request**. GitHub will fork the repo for you.
5. Wait for the **Registry check** to run on your PR:
   - **Red ✗:** read the message, fix your file, and the check runs again.
   - **Green ✓:** the instructor reviews and merges, and your team appears in the directory within a minute or two.

The check enforces three things: your link and chain are the ones you were assigned, the person opening the PR is a listed member, and no two teams share a name.

## Instructor setup

1. Create a GitHub organization for the course (free), then create this repo inside it. Copy all files, including `.github/`.
2. Go to **Settings → Pages** and set Source to **GitHub Actions**.
3. Go to **Settings → Branches** and add a rule for `main`: require a pull request, and require the **Registry check** status to pass.
4. Before class, add each team's slug, link and chain to `assignments.json`. As the org owner you can commit directly to `main`, provided the branch rule allows admin bypass.
5. Delete `teams/example-team.json` and its assignment once real teams have joined.
