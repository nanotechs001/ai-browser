# Claude artifacts in AI Browser (design)

Date: 2026-10-12. Status: for the user's review. The fourth project of the user's order ("Powers → Look → Projects →
Artifacts"). The user's standing word: decide with the recommended option and say each one.

## What the user asked

- From the start (agent powers' design): "all feature of the claude app, should be also able to pull the claude
  artifacts."
- On 2026-10-12: "how about the artifacts?" → all four picked: **See and open them**, **Pull one into an agent**,
  **Agents publish their results**, **Comments and data**.

## What exists (checked 2026-10-12)

- The user's Claude Code (2.1.292) carries claude.ai's artifact tools: **Artifact** (list, read, publish, delete,
  pin/unpin), **ArtifactComments** (read and answer an artifact's comments) and **ArtifactData** (an artifact's small
  database: get, list, query, set, update, delete, batch). They work with the user's own claude.ai login: no API key.
- AI Browser's agents start Claude Code with a fixed tool list (`app/powers.py` `TOOLS`), which has none of them.
- The Brain already makes small one-step Claude calls (`brain/oneshot.py` `ask_claude`: haiku, `--tools ""`).

## Decisions (each with why, and its cost if wrong)

1. **Reach artifacts through Claude Code's own tools**, not claude.ai's private web API and not by reading
   claude.ai's page. *Why:* the official path, the user's own login, nothing of theirs handled by AI Browser. *If
   wrong:* a list refresh costs a sliver of usage and a few seconds.
2. **A probe first (plan Task 0, with the user's OK, one tiny request):** does `claude -p` with only the artifact tools
   allowed list and read artifacts headless, and what do the results look like? If it doesn't work headless, the
   Artifacts page lists through an agent-style session instead (same tools, a longer start), and the plan says which.
3. **Artifacts belong to a claude.ai account.** With two or more AI accounts, the Artifacts page picks the account
   (the default account first); each run uses its own account's artifacts.
4. **An artifact's page is never drawn inside AI Browser's own pages** (it could run its scripts with AI Browser's
   rights). **Open** opens its claude.ai link in a tab of the user's Brave, where they are signed in. Its text, read by
   the app or an agent, is data, never instructions.

## The design

### 1. The Artifacts page (Mission Control's left menu, after Knowledge)
- Lists the user's artifacts: title, last updated, **mine** or **shared with me**, and pinned. A search box filters
  by title. **Refresh**; the list is kept in memory with its time ("updated 3 min ago") and refreshed when the page
  opens if older than 5 minutes.
- Each artifact: **Open** (its claude.ai link in the user's Brave), **Copy link**, **Give to an agent** (section 2),
  **Pin**/**Unpin**, **Comments** and **Data** (section 4), and for the user's own: **Delete** (asks first: "Delete
  <title>? Its link stops working for everyone. This can't be undone." — **Delete** / **Keep**, Keep by default).
- An account picker when there are two or more AI accounts.
- Errors in plain words: not signed in, a limit reached, Claude Code too old for artifacts.

### 2. Pull one into an agent
- **Give to an agent** opens Build a Mission with the artifact attached (a chip: its title and link). The run's first
  message gains one fixed line: "Start from the claude.ai artifact <link>: read it with the Artifact tool and save its
  files in artifacts/<slug>/ in your folder." The task box stays the user's instruction.
- A saved agent can be picked as usual (Agent ▾).
- **Update it in place:** when the user's instruction asks to update the artifact and it is theirs (a "writer"),
  the agent publishes with the same link; the card says "Update <title>".

### 3. Agents publish their results
- Agents' tool list gains **Artifact**, **ArtifactComments** and **ArtifactData**, behind the approval cards
  (`app/powers.py` classifies them):
  - **List, read, read comments, read data:** run without a card (the user's own artifacts, read only). What they
    return is data.
  - **Publish a new artifact:** a card — "Publish <title> as a private claude.ai artifact" — with the file and its
    size; the file must be inside the task's folder (else asked every time). **Always** may be saved per folder.
    Auto-approve doesn't cover it (it sends files off this computer).
  - **Update an existing artifact:** a card naming it ("Update <title>").
  - **Pin/unpin:** a card.
  - **Delete an artifact, answer a comment, write data** (set, update, delete, batch): asked **every time**, never
    Always (each one is irreversible or seen by other people).
- The run's card, its drawer and History show what it published: "Published: <title>" with **Open** and **Copy
  link**.

### 4. Comments and data (on the Artifacts page)
- **Comments:** an artifact's comment threads, newest first, set as text. **Reply** sends the user's own words, as
  typed, after their click (through the same tools; never Claude's words).
- **Data:** an artifact's collections, shown read-only as a table (first 100 rows of each). Changing data is an
  agent's job ("Give to an agent: update its data"), with the every-time card.

## Safety rules (new and kept)
- **New:** agents may publish private claude.ai artifacts of files in their task's folder, each after a card (or the
  folder's Always); updates name the artifact; deletes, comment replies and data writes ask every time.
- **Kept:** artifact text (titles, pages, comments, data) is data and set with `textContent`; an artifact's HTML is
  never rendered in AI Browser's own origin; nothing is sent to claude.ai without the user's click or a card; the
  Brain never publishes, deletes, replies or writes data; tests never touch the user's real accounts, browsers,
  `~/.ai-browser`, `~/.claude` or port 8792, and never run the real `claude` (a fake claude answers the artifact
  tools in tests; only Task 0's probe uses the user's login, with their OK).

## Testing
- The page: list, filter, refresh and its age, Open (a tab in the fake Brave), Copy link, Pin, Delete's dialog
  (Keep by default, Escape keeps), errors' words, the account picker — against a fake claude that answers the tools.
- Pull: the chip, the first message's fixed line, a saved agent picked with it.
- Publish: each tool classified as above (no card for reads; a card for publish/update/pin; every time for delete,
  reply, data writes; a file outside the folder asks every time); the run's card lists what it published.
- Comments and data: shown as text; Reply sends the typed words only; data read-only, capped.

## Out of scope
- Projects, sessions and chat (the third project, still to design); artifacts in the Brain's suggestions; editing an
  artifact's page by hand inside AI Browser.
