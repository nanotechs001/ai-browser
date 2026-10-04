# AI accounts: several Claude logins, picked per agent, carried past a limit

Date: 2026-10-04.

## Status

The user approved the design's two sections in chat ("yeah"). This spec writes them down with the technical design.
The user reviews it before the plan is written.

**The user's request**, verbatim: "How I will be able to switch account on my AI? I have a second claude that I launch
from open -n -a 'Claude' --args --user-data-dir="$HOME/.claude-second" and also possibly a codex AI to use or gemini."

**Their answers:**
- **Why switch:** "Keep working past a limit", "Separate work and personal", "Best AI per task".
- **At a usage limit:** "Ask me, then carry on (Recommended)", confirmed later as "Ask me with one click
  (Recommended)". Nothing switches without the user's click.
- **The Brain:** "One account, set in Settings (Recommended)".
- **Carrying on:** "Both: move, else hand over (Recommended)".
- **Where to see them:** asked "where can i see all the connected ai acc?"; the answer is Settings → Accounts.

**Scope:**
- **In:** Claude accounts.
- **Out, for the next design:** Codex and Gemini ("Best AI per task"). Each needs an adapter for its own command-line
  tool. They will join the same account list: an account gets a `kind`, which is "claude" here.

**Where it sits:** after wave B (`app-window`), which adds `settings.py` and the Settings page this builds on. Whether
it comes before or after waves C (`browser-profile-choice`) and D (`side-chat`) is the user's call. Recommended: right
after B, since a limit stops work today.

## Facts this rests on

Checked on 2026-10-04 on the user's Mac, with Claude Code 2.1.263.

- **A separate login per folder.** Setting `CLAUDE_CONFIG_DIR` gives a separate login, with its own macOS Keychain
  entry (Claude Code docs, authentication, "Log in with multiple accounts").
- **Sign-in is interactive.** The user runs `claude` with that folder and signs in through their browser. There's no
  documented non-interactive login.
- **`claude auth status` reports a login without a model turn.** It prints JSON:
  - always: `loggedIn`, `authMethod` and `projectsDirectory`;
  - when signed in, also `subscriptionType` (for example "pro"), `email`, `orgId` and `orgName`.

  In an empty folder it answers `loggedIn: false`, and it creates `.claude.json` and `backups/` there.
- **Conversations live in each account's folder:** `<folder>/projects/<encoded working folder>/<session id>.jsonl`.
  `--resume` looks only under the current folder. Copying a conversation to another folder isn't documented.
- **A usage limit in `stream-json` output isn't documented.** The Claude Code binary carries a `rate_limit_event` type
  and the texts "usage limit reached" and "you have reached your weekly usage limit".
- **AI Browser starts Claude Code in three places.** Each copies the environment without `ANTHROPIC_API_KEY` and
  `ANTHROPIC_AUTH_TOKEN`:
  - `app/bridge.py`: each agent, a long-lived `stream-json` process that resumes with `--resume <session id>`. Its
    working folder is `<home>/app/agents/<id>/chat`;
  - `brain/oneshot.py`: `ask_claude`, used by the Brain's service and its skill writer;
  - `brain/tools.py`: the tools probe.
- **The desktop app's `--user-data-dir` is a different thing.** It holds the Claude desktop app's own data, not Claude
  Code's. AI Browser never uses the user's `~/.claude-second`.

## Decisions

1. **An account** is an id, a name and a folder.
   - **The name** is the user's label, at most 40 characters, cleaned the way profile names are (no control, format or
     bidi characters).
   - **The id** is made by AI Browser (`acct-` and 6 random hex characters). Only the id reaches a command line or a
     path.
   - **"Default"** is built in: the user's own login, which is the environment's `CLAUDE_CONFIG_DIR` if it is set, else
     `~/.claude`. It can't be removed.
   - **Storage:** `<home>/accounts.json` (mode 0600) holds
     `{"accounts": [{"id", "name", "folder"}], "default": "<id>", "brain": "<id>"}`. A bad or missing file means
     Default only, and it never raises.
2. **Adding an account** (Settings → Accounts → **Add**):
   - **The folder:** the user types a name, and AI Browser makes `<home>/accounts/<id>/` (mode 0700).
   - **"Use a Claude Code folder I already have"** takes an existing folder instead. A browser profile is refused: a
     folder holding `Local State`, `Preferences` or `Cookies` at its top is Chromium or Electron data.
   - **Signing in:** the account shows **Sign in** with two ways:
     - **Open Terminal** opens a terminal window running `claude` with `CLAUDE_CONFIG_DIR` set to the folder. On macOS
       that's a Terminal window, and on Windows a `cmd` window. The folder path is AI Browser's own, and it is quoted;
     - **Copy the command** is for the user's own terminal.
   - **The user signs in** in that terminal and their browser. AI Browser never sees a password or a token.
3. **Seeing accounts** (Settings → Accounts):
   - each account shows its name, **Signed in · Pro** or **Not signed in**, and which one is the default and which one
     the Brain uses;
   - the status comes from `claude auth status`: when the page opens, then every 5 s while an account is waiting for
     its sign-in;
   - **only `loggedIn` and `subscriptionType` are kept.** The email, the organisation and their ids are never stored,
     shown or logged.
4. **Choosing:**
   - **In Settings:** "Default account for new agents" and "The Brain's account".
   - **When starting an agent:** AI Home's new-task form and Mission Control's new agent get an **Account** picker next
     to the model picker, set to the default.
     - A signed-out account is disabled: "Sign in first".
     - An account at a known limit says "at its limit until 3:00 pm", when Claude Code gave a time.
   - **On each agent:** its row in AI Home and its drawer in Mission Control show the account's name.
   - **An agent keeps its account** until it is moved.
5. **Running on an account:** one helper, `accounts.env_for(account)`, returns the environment without the two API
   variables.
   - For any account but Default, it sets `CLAUDE_CONFIG_DIR` to that account's folder. Default leaves the environment
     as it is.
   - It is used at all three start points: the agent's own account, the Brain's account for `ask_claude` (the Brain and
     the skill writer), and the account being probed for tools.
6. **What's per account and what's shared:**
   - **Per account:**
     - the login;
     - Claude Code's own settings;
     - MCP servers and claude.ai connectors;
     - conversations.

     The Tools page lists each account's tools, and `tools.json` keeps its lists per account. An agent gets only its
     own account's tools and allows.
   - **Shared:**
     - AI Browser's skills (served by AI Browser's MCP; personal skills still come from Default's `skills/`);
     - workflows;
     - the browser connection and the tabs the user handed over;
     - the Brain's inbox.
7. **Noticing a limit:**
   - **For an agent:** `bridge.py` marks the agent `limit` when either of these arrives:
     - a `result` event with `is_error` and a usage-limit text ("usage limit reached", "reached your weekly usage
       limit", or "limit reached|<epoch seconds>");
     - a `rate_limit_event` whose `status` is "rejected".

     The undocumented event is read defensively: only `status`, `resetsAt` and `rateLimitType`, and only when they are
     well-typed.
   - **What's kept:** the account and the reset time, if any. The account's "limit until" is remembered for this app
     run, for the pickers.
   - **Unknown event types** are logged by type and keys only, so the first real limit shows the event's real shape.
   - **For the Brain:** a failed `ask_claude` with a limit text marks the Brain's account the same way.
8. **The ask:**
   - **Where:** the agent's row in AI Home and its drawer in Mission Control say "Personal hit its usage limit (resets
     3:00 pm)." with two buttons:
     - **Continue on Work**, with a picker when more than one other account is signed in;
     - **Wait for the reset**, which leaves the agent paused with the Continue button still there.
   - **With no other signed-in account:** only Wait shows, and the row says "Add an account in Settings".
   - **Clicks only.** The click sends `account_move`, which is app-only in `MESSAGE_RULES`. The watcher, the Brain and
     voice never move an agent.
9. **Moving an agent** (`account_move` {id, account}), one move per agent at a time:
   1. If the agent's Claude Code process still runs, it is stopped (the agent ended its turn at the limit anyway).
   2. **Move the conversation:**
      - find `<from>/projects/*/<session id>.jsonl` and copy it, with a folder of the same name beside it if there is
        one, to `<to>/projects/<the same folder name>/`;
      - nothing that exists there is overwritten, and the copy is mode 0600;
      - the original stays: AI Browser never deletes a conversation.
   3. Start the agent on the new account with `--resume <session id>` and the message "Continue the task.".
   4. **If that fails** (no conversation found, or the process ends at once), start a fresh session on the new account
      with a hand-over note:
      - the task;
      - the agent's last steps and messages, taken from AI Browser's own log, at most 20,000 characters. Page text in
        it stays marked as page data;
      - the titles and addresses of its open tabs.
   5. The agent's account is now the new one. The row says "Moved to Work with its conversation" or "Started fresh on
      Work with a hand-over note".
   6. Its tabs stay its own: the browser connection doesn't change.
10. **The Brain at a limit:** a card in AI Home's Brain area says "The Brain hit its limit on Personal. Continue on
    Work?". The click sets the Brain's account in Settings, where the user can change it back, and retries the failed
    call once.
11. **After a reset:** nothing moves back by itself. An agent can be moved back from its row: the same **Continue on**,
    offered while the agent is idle.

## Safety

- **No credentials.** AI Browser never reads, stores or passes a token or a password. The user signs in themselves in
  a terminal and their browser. Never `--bare`, and never API keys: both variables are stripped at every start point.
- **No emails.** `claude auth status`'s email, organisation and ids are never stored, shown or logged.
- **Account folders:** mode 0700. `accounts.json`: mode 0600. Only AI Browser's own ids reach a command line or a
  path.
- **Moving is a click.** It's app-only in `MESSAGE_RULES`: never the watcher, never the Brain, never voice.
- **Page text stays data**, in the hand-over note too.
- **Removing an account** only makes AI Browser forget it. Its folder, conversations and sign-in stay.

## Interfaces

- **`src/ai_browser/accounts.py` (new):**
  - `Account(id, name, folder, kind="claude")`;
  - `Accounts(home)` with:
    - `list()`, `get(id)`;
    - `add(name) -> Account`, `add_existing(name, folder) -> Account`, `remove(id)`;
    - `set_default(id)`, `set_brain(id)`;
    - `env_for(id) -> dict`;
    - `status(id) -> {"signed_in": bool, "plan": str | None}`, which runs `claude auth status` with the account's
      folder, has a 5 s cache, and never raises;
    - `limit(id) -> float | None` and `set_limit(id, resets_at)`.
- **The move** (in `app/agents.py`, or a small `app/move.py`): `move_conversation(from_folder, to_folder, session_id)
  -> bool` and `handover_note(agent) -> str`.
- **Server messages, all app-only in `MESSAGE_RULES`:** `accounts`, `account_add`, `account_add_existing`,
  `account_remove`, `account_default`, `account_brain`, `account_signin` (Open Terminal), `account_move`.
- **What pages get:**
  - the snapshot's `accounts`: `[{id, name, signed_in, plan, limit_until, default, brain}]`;
  - each agent's `account` (id and name) and `limit` (account and reset time).

  `accounts` stays out of `WATCHER_RECEIVES`.

## Testing

- **The fake `claude` gains:**
  - `auth status`, answered per `CLAUDE_CONFIG_DIR`: a marker file in the folder means signed in;
  - a scripted usage-limit result, and a scripted `rate_limit_event`;
  - `--resume` that finds the conversation only under its own `CLAUDE_CONFIG_DIR`.
- **Tests:**
  - **`env_for`:** Default leaves the environment as it is; the others set `CLAUDE_CONFIG_DIR`; both API variables are
    gone either way;
  - **`accounts.json`:** a round trip, and bad or missing files;
  - **status:** no email or organisation anywhere, on any page or in any log;
  - **noticing a limit:** each text, the rejected event, a malformed event, and unknown events ignored;
  - **the move:**
    - the conversation is copied and resumed;
    - nothing is overwritten;
    - a missing copy, or a resume that fails, falls back to the hand-over note;
    - a second move while one runs does nothing;
  - **rights:** a watcher socket can't send any `account_*` message;
  - **the pages:** the picker, the row's ask, Settings → Accounts, the Brain's card, all with `textContent` only.
- **The first build task is a probe on the user's Mac, with their second account signed in.** It copies a real
  conversation and resumes it under the other folder. If it fails, the hand-over note becomes the only way to carry
  on, as a ruling.
- **The user's hand check:**
  - add a second account and sign it in from Settings;
  - start an agent on it;
  - when an account hits its limit, click **Continue on …** and see the agent carry on.

## Review Focus

These are the failures most likely to bite:
1. **The user's environment already sets `CLAUDE_CONFIG_DIR`.** Default must mean that folder, not `~/.claude`.
2. **A signed-out account picked anyway** (it signed out after the page loaded). The agent's row says "Work isn't
   signed in: sign in from Settings → Accounts". The agent never falls back to another account by itself.
3. **Two agents moving to the same account at once, or a conversation id already in the target folder.** Nothing is
   overwritten, and each move finishes on its own.
4. **A limit message split across reads, or a limit that arrives mid-turn.** It's noticed once, and the agent's
   partial answer stays in its chat.
5. **The hand-over note holding page text that looks like instructions.** It stays marked as page data, like every
   other page text an agent reads.
