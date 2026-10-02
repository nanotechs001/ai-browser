# Mission Control: the agents at work in 3D, and the Brain that talks back (project 6)

Date: 2026-10-02.

**Status:** written and self-reviewed without a review round. The user said: "where is the UI 3d i am talking about for
the agents who are working? then the brain? proceed to build it after you finish all the tests complete the task, do
not ask for my input for now". Design decisions the user would normally weigh in on are marked **Assumed**. The user
reviews the result.

**The user's vision**, from planning project 5: "a visual like UI 3d or AI agents that working in a virtual computer
and the main brain animating like a and AI blurb that will talk back".

**Builds on:** AI Browser (projects 3–4: the app server, AgentManager, AI Home, thumbnails) and the Brain (project 5:
the BrainService, the inbox, permission requests).

## Goal

A page in AI Browser, **Mission Control**, that shows the user's AI team at work:
- **every agent** is a little robot at its own workstation in a 3D room:
  - its monitor shows the tab it works in, live;
  - a ticker says what it just did;
  - a light shows its state;
- **the Brain** sits in the middle as an animated, glowing blob:
  - it breathes when idle;
  - it swirls while it sorts messages or writes a draft;
  - it glows warm when something needs the user;
  - it pulses when it speaks;
- **the Brain talks back**, in short updates: written in a speech bubble, and spoken aloud if the user switches Voice
  on;
- **everything can be done from there:**
  - open an agent: its chat, Watch, Stop, Close, and its permission card;
  - open the Brain's inbox;
  - give an agent a new task.

Success means:
1. **The room:** opening Mission Control (AI Home's **Mission Control** button) shows the room in under a second.
   - Every agent has a station around the Brain.
   - A new agent's station appears with a short animation, and a closed agent's station goes.
   - Updates change stations in place: a click is never lost to a rebuild.
2. **Live screens:**
   - a working agent's monitor shows its tab's picture, updated after its actions (the same pictures as AI Home);
   - its ticker shows the last action ("click e14 · 38 ms");
   - a Mission Control opened later shows the latest pictures at once.
3. **Needs you:** an agent waiting for a tool permission makes its station glow and show **needs you**.
   - Clicking the station opens a drawer with the permission card (**Allow once**, **Always allow**, **Deny**) and the
     agent's chat.
   - The answer reaches the agent exactly as from AI Home.
4. **The Brain blob:**
   - it **breathes** while idle and **swirls** while the Brain sorts, drafts or thinks;
   - it **glows** while items need the user, with their count under it;
   - clicking it opens the Brain's inbox in the drawer: the same inbox as AI Home, with Draft reply, Approve and the
     rest.
5. **Talking back:**
   - **What becomes an update:** a new item that needs the user, an agent that finished or failed, an agent waiting for
     a permission, and a draft that is ready.
   - **Bubbles:** each update shows in a speech bubble from the blob, one at a time. More than three waiting become one
     summary ("4 more updates").
   - **Voice:** with **Voice** on, updates are also spoken, only with voices that run on this Mac. It is off by default,
     and the choice is remembered.
6. **Moving around:**
   - **mouse:** drag to turn the room, scroll to zoom, double-click to reset;
   - **keyboard:** arrow keys turn, + and − zoom, 0 resets;
   - **reduced motion:** with Reduce Motion set on the Mac, idle animations stop and the blob moves slowly.
7. **Text stays text:**
   - every name, title, action and summary is set with `textContent`;
   - screens show only the app's own JPEG pictures;
   - nothing is sent anywhere new.

## What the user sees

### Opening it

- **AI Home's header** has a **Mission Control** button. It opens `mission.html` in a tab, reusing one already open.
- **Mission Control's top bar** has an **AI Home** link back.

### The room

- **Look:** a dark control room (**Assumed**: dark always, as a control room is). A floor grid fades into the distance
  with a soft glow under the Brain.
- **The Brain** floats in the middle, at the back, over a glowing ring.
- **Stations** stand in an arc in front of it, facing the user: up to 5 in the first arc, and the rest in a second arc
  behind.

### A station

- **The parts:**
  - a desk with a monitor;
  - a small round robot in the agent's colour (the same colour as its Chrome tab group);
  - a nameplate with the agent's name;
  - a state light;
  - a ticker under the monitor.
- **The monitor** shows the agent's working tab: the thumbnail AI Home also shows. Before the first picture, it shows a
  blank screen with the agent's colour.
- **States:**
  - **working:** green light; the robot types (bobs), and the screen has a soft scan line;
  - **waiting in line:** amber light; the robot sits still;
  - **needs you:** accent-coloured glow around the station, a pulsing **needs you** badge, and the robot raises a hand;
  - **your turn (done):** a calm check;
  - **stopped:** grey;
  - **failed:** red light, with the reason in the ticker.
- **Clicking a station** (or Enter on it) opens the drawer for that agent.

### The heads-up display (flat, over the room)

- **Top bar:**
  - "Mission Control" and the connection dot;
  - counts ("2 working · 1 needs you · 3 done");
  - the **Voice** switch;
  - **List** (the stations as a plain list);
  - **AI Home**.
- **Bottom bar:** "Give an agent a task", like AI Home's new task box, with a model picker.
- **Right drawer:**
  - **for an agent:** its name, state and status; Watch, Stop, Close; its permission card when one waits; and its chat
    (the same chat AI Home shows);
  - **for the Brain:** its inbox.
- **The speech bubble** sits above the blob, with the Brain's latest update.

## Decisions

### 1. A page of AI Browser's extension

- **Files:**
  - `mission.html`, `mission.css`;
  - `mission.js`: connection, state, top and bottom bars, drawer;
  - `scene.js`: the 3D room, stations and camera;
  - `blob.js`: the Brain's WebGL blob;
  - `voice.js`: the updates and speech.
- **Connection:** it connects with `link.js` (view "mission") like AI Home: the same token, origin and messages.
- **Reuse:** the chat (`chat.js`), the permission card (`permission.js`) and the Brain's inbox (`brainui.js`).

### 2. Drawn without libraries

- **The room and stations:** CSS 3D transforms (`perspective`, `preserve-3d`). Text stays crisp, clicks are ordinary DOM
  events, and `textContent` is used throughout.
- **The Brain:** one WebGL canvas. A fragment shader ray-marches a sphere whose surface moves with layered noise, lit
  with a soft rim and an inner glow. Its uniforms are the state (idle, thinking, alert, speaking), the time, and a pulse.
- **Without WebGL,** the blob is a CSS gradient orb with the same states.
- **Why not three.js:**
  - an MV3 page can only run scripts packaged with the extension;
  - packaging a library means downloading it, which needs the user's OK (the user asked not to be asked now);
  - the room needs only boxes, planes and one shader.

### 3. Data: the messages AI Home has, plus two

- **Already there:** `snapshot`, `agent`, `agent_closed`, `agent_event`, `thumb`, `brain_*`, `permission_request`,
  `created`, `error`.
- **New: thumbnails for a page opened later.** The app server keeps each agent's latest thumbnail.
  - `thumbs {}` is answered with `{"type": "thumbs", "thumbs": {agent_id: jpeg}}`.
  - A closed agent's thumbnail is dropped.
- **New: what the Brain is doing.** The BrainService broadcasts `{"type": "brain_activity", "busy": bool, "what":
  text}`:
  - when a batch starts and ends being sorted ("Sorting 4 new messages from Gmail");
  - when a draft starts and ends ("Drafting a reply to Maria");
  - when a Tell is mapped ("Thinking about your answer").

### 4. Talking back

- **The updates:** written in plain words from the messages:
  - "Maria Santos needs your reply: she asks to move the launch.";
  - "Fix the footer is done.";
  - "Fix the footer wants to use ClickUp: create task. It's waiting for you.";
  - "Your reply to Maria is ready to check.".

  They use the Brain's one-line summary and the agent's name, never a whole message. A Mission Control opened later
  doesn't replay old events: only what happens while it is open.
- **The queue:**
  - one update at a time, each shown for about 5 s, or until its speech ends;
  - more than 3 waiting become "N more updates: open the Brain".
- **Voice:**
  - **Engine:** the browser's `speechSynthesis`, with a voice whose `localService` is true, so the text never leaves
    the Mac. If there is none, Voice says so and stays off.
  - **Off by default**, and remembered in `chrome.storage.local`.
  - The blob is "speaking" while a voice speaks.

### 5. Camera and performance

- **Camera:** the room is one element under `perspective`. Turning sets the room's `rotateX` (tilt, 35°–70°) and
  `rotateZ`; zoom is a scale (0.6–1.6).
- **The blob canvas:**
  - at most 360 CSS pixels and a device pixel ratio of at most 2;
  - drawn with `requestAnimationFrame`, which stops on its own while the tab is hidden;
  - drawn only while it changes, in reduced-motion mode.
- **Station updates** change only the parts that changed: text, classes and the image `src`.

### 6. Entry point

- AI Home's **Mission Control** button opens it.
- **Assumed:** no `ai mission` address-bar shortcut. "ai " followed by a task already starts an agent, and a task could
  begin with "mission".

## Messages

- **Page → server:** `thumbs {}`, plus the existing `new_task`, `events`, `watch`, `stop`, `close`, `permission`,
  `brain`, `draft`, `approve`, `hand`, `tell`, `done`.
- **Server → pages:** `thumbs {thumbs}` and `brain_activity {busy, what}`.

## Safety

AI Home's rules hold:
- text only, with `textContent`;
- pictures only as `data:image/jpeg;base64,` from the app;
- no new permissions in the manifest;
- the same token and origin checks.

New:
- **Speech** uses only on-device voices (`localService`). Network voices would send the spoken text to their provider.
- **What is spoken or shown in bubbles:** only the Brain's one-line summaries, senders' names and agents' names. Never a
  message body, a page's text, or a tool's input. The permission card in the drawer shows the input, as text, like
  everywhere else.
- **Mission Control adds no new way to act.** Every button sends a message AI Home already sends (`permission` only
  from the card's buttons).

## Testing

- **Server:**
  - the latest thumbnail is kept per agent and returned by `thumbs`, and dropped when the agent closes;
  - `brain_activity` goes out busy, then not busy, around a sort, a draft and a Tell (fake claude).
- **Mission Control in headless Chrome** (AI Home's test stack):
  1. **Stations:**
     - one per agent, with names as text (a hostile name stays text);
     - updated in place: the same element before and after an update;
     - a closed agent's station is removed.
  2. **Screens:** a `thumb` sets the monitor's image to that JPEG, and a page opened later gets it from `thumbs`.
  3. **Needs you:**
     - a waiting permission puts **needs you** on the station;
     - clicking the station shows the card in the drawer;
     - **Allow once** reaches the fake claude as an allow.
  4. **The blob:**
     - its state is `idle`, then `thinking` on `brain_activity` busy, then `alert` while needs-you items exist;
     - the count shows under it;
     - clicking it shows the Brain's inbox in the drawer.
  5. **Updates:**
     - a needs-you item and an agent finishing each produce a bubble with the right words, in order;
     - a burst becomes a summary;
     - the Voice switch is remembered;
     - with no on-device voice, Voice reports that it is off.
  6. **Camera:** arrow keys and zoom change the room's transform within its limits; 0 resets.
  7. **New task:** the bottom box creates an agent.
- **Screenshots** of the room with sample agents and a waiting permission, checked by eye.

## Out of scope

- **Talking to the Brain by voice** (the microphone, speech to text): a later project.
- **Live video of agents' screens:** thumbnails only.
- **VR, external 3D libraries, avatars beyond the simple robot.**
