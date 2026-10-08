# Named missions, the Brain's hand-offs, its sources, and Ask AI's history (design)

Date: 2026-10-08. Status: the user's choices made (below); for building.

## What the user asked (verbatim)

"another changes, building a mission user should be able to set name for this agent and what it will be working on
short description. The brain is able to delegate task automatically on existing agents that are working based on the
context it recieved from the chats or any sources it is listening to. for brain setting user should be able to check
or uncheck what it will be listenting or watch add add an instruction to brain to notify user that it is delegating a
task to existing agent or if it will suggest to create it's own agent and read the instruction it will assign on that
agent. Also the ask AI chatbox it should be faded effect from bottom to top fade and will be solid background if mouse
is hover and can scroll the previous conversation. you can remove the use a template and templates in dashboard tab"

Their choices:
- **Delegation:** "Auto, with a Cancel window: the Brain notifies you ("Giving agent 2: …", with the exact instruction)
  and sends it after 15 seconds unless you press Cancel. Only to agents already working; a new agent is still a
  suggestion you Start. Instructions that come from emails or Slack messages always wait for your OK."
- **Sources (each a checkbox):** agents' chats and results; inbox: Gmail, Slack, Asana; watched page parts; the
  floating chat.

## The design

### 1. Named missions
- **Build a Mission** gets two short fields above the box: **Name** ("Name this agent", at most 60 characters) and
  **What it works on** (a one-line description, at most 160 characters). Both optional.
- An agent keeps `name` and `description`. The name shows wherever the agent's task line shows today: the desk's
  nameplate ("2 · Research competitors"), Current Task, My Missions, History, the drawer, AI Home. The description shows
  under the name in Current Task and the drawer, and as the tooltip elsewhere. Without a name, today's words stay.
- Names and descriptions are text only (`textContent`), cleaned like workspace names (no control or direction
  characters), and never sent to Claude as instructions: the task box stays the agent's instruction.

### 2. Templates leave Mission Control
- The composer loses **Use a Template**; the left menu loses **Templates**. Templates stay in AI Home (Run, Edit, New),
  and the Calendar still shows scheduled templates: a click opens AI Home at its templates.
- Workspaces keep counting their templates; moving a template between workspaces stays out of Mission Control for now.

### 3. Ask AI's history
- Ask AI shows the conversation with the Brain above the box: the newest at the bottom, older lines fading out
  towards the top (a mask, bottom solid to top clear).
- On hover (or focus inside it) the area turns solid and scrolls; the wheel scrolls the history, not the office.
- History is this run's talk with the Brain (as the talk panel keeps it today); text only.

### 4. What the Brain listens to (Settings → Brain)
- Checkboxes, each on by default except the inbox sites, which keep today's switch state: **Agents' chats and results**,
  **Gmail**, **Slack**, **Asana**, **Watched page parts**, **The floating chat**.
- Unchecked means the Brain is never sent that source's content (an unchecked inbox site isn't read at all, as today's
  switch).

### 5. The Brain hands tasks to working agents (15 seconds to Cancel)
- The Brain may decide that a working agent should take something on. It then shows a **hand-off card** (in its inbox,
  the globe's bubble and a notification): "Giving **agent 2 · Research competitors**:" followed by the exact
  instruction, with **Send now** and **Cancel**, and a 15-second countdown. At zero it sends the instruction to that
  agent as a message (exactly as the user's Send would), and the card says "Sent to agent 2".
- **Only to agents already working** (working, waiting, or needs you), never to a finished one, and never a new agent:
  a new agent is a **suggestion** card with the exact instruction and **Start**, as today.
- **Untrusted sources always wait:** when what led to the hand-off came from an email, Slack or Asana message, or a
  watched page part, the card has no countdown: it waits for **Send** (the instruction may carry someone else's words).
  Only the user's own words (Ask AI, the floating chat) may start a countdown; an agent's result waits for **Send**
  too (agents read web pages; the user's choice, 2026-10-08).
- **The user stays in charge:** Settings → Brain → **"Hand tasks to working agents by itself (15 s to cancel)"**, on by
  default; off means every hand-off waits for Send. Stop on an agent cancels any countdown for it. Closing the app
  cancels all countdowns (nothing is sent while nobody can see it).
- **The Brain's instruction (its prompt):** when it hands something to an agent or suggests a new one, it must say so in
  one plain line and give the exact instruction it will send; it never hides an instruction, and never sends anything
  else.
- Every hand-off is recorded (the agent's chat shows "From the Brain: …"; the Brain's inbox keeps the card).

## Safety rules that change, and those that stay
- **Changes (the user's choice):** the Brain may send an instruction to a working agent without a click, after a visible
  15-second countdown the user can cancel, and only when the trigger was the user's own words.
- **Stays:** inbox and page text is data; text from emails, Slack, Asana or watched pages never reaches an agent without
  the user's Send; the Brain never starts a new agent by itself; hand-over of tabs and taking them back stay clicks;
  pages set text with `textContent`; every new page message is app-only in `MESSAGE_RULES` with its copy in
  `tests/test_watcher_rules.py`; tests never touch the user's real browsers, `~/.ai-browser`, `~/.claude` or port 8792.

## Testing
- Named missions: fields, limits, cleaning, shown in each place, absent → today's words.
- Templates gone from the composer and menu; the Calendar's template opens AI Home.
- Ask AI: the history shows, fades (mask present), turns solid on hover, scrolls.
- Sources: each checkbox stops its content reaching the Brain (fake inputs), and persists.
- Hand-offs: a countdown card sends after 15 s (fake clock); Cancel and Stop cancel it; an untrusted trigger has no
  countdown; the switch off → no countdown; only working agents; a new agent stays a Start suggestion; the exact
  instruction shown is the one sent; app-only messages.
