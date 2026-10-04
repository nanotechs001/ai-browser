// AI Home → Train a new agent: the Brain drafts a skill (SKILL.md) from what the user describes, or from a finished
// agent's chat (Save as skill). The draft is plain text to read and edit; only Save writes it, to ~/.claude/skills,
// never over an existing skill (Update shows the diff first). Try it starts an agent with the draft, writing nothing.
import { el } from "./chat.js";

function nameOf(text) {
  const found = /^name:\s*["']?([^"'\n]+?)["']?\s*$/m.exec(text);
  return found ? found[1] : "";
}

export function mountTrain(root, link, { tabs = () => [], model = () => "sonnet" } = {}) {
  const job = el("textarea", "job");
  job.rows = 3;
  job.placeholder = "What should the agent do? For example: build Elementor landing pages the way I like";
  const examples = el("textarea", "examples");
  examples.rows = 2;
  examples.placeholder = "Examples or rules (optional): pasted text, what you always want, what to avoid";
  const page = el("select", "page");
  const draft = el("button", "draft primary", "Draft the skill");
  const status = el("span", "status muted");
  const start = el("div", "row");
  start.append(page, draft, status);
  const editor = el("div", "skill-editor card");
  editor.hidden = true;
  const title = el("div", "row");
  const name = el("strong", "skill-name");
  title.append(el("span", "muted", "Skill:"), name);
  const text = el("textarea", "skill-text");
  text.rows = 14;
  text.spellcheck = false;
  const save = el("button", "save primary", "Save");
  const task = el("input", "try-task");
  task.placeholder = "A test task for Try it";
  const tryIt = el("button", "try", "Try it");
  const discard = el("button", "discard ghost", "Discard");
  const result = el("span", "result muted");
  const buttons = el("div", "row");
  buttons.append(save, task, tryIt, discard, result);
  const exists = el("div", "exists row");
  exists.hidden = true;
  const saveAs = el("button", "save-as");
  const update = el("button", "update", "Update the existing skill");
  exists.append(saveAs, update);
  const diff = el("pre", "diff");
  const confirm = el("button", "confirm-update primary", "Yes, update it");
  diff.hidden = confirm.hidden = true;
  editor.append(title, text, buttons, exists, diff, confirm);
  root.replaceChildren(job, examples, start, editor);
  let pending = null;

  function request() {
    pending = `k${Date.now()}`;
    return pending;
  }

  function send(message) {
    const sent = link.send(message);
    if (!sent) status.textContent = "Not connected: is ai-browser app running?";
    return sent;
  }

  function pages() {
    const current = page.value;
    const none = el("option", "", "No page to look at");
    none.value = "";
    page.replaceChildren(none);
    for (const tab of tabs()) {
      const option = el("option", "", `Look at: ${tab.title || tab.url}`.slice(0, 90));
      option.value = tab.target;
      page.append(option);
    }
    page.value = [...page.options].some((option) => option.value === current) ? current : "";
  }

  function clearAnswers() {
    exists.hidden = diff.hidden = confirm.hidden = true;
    result.textContent = "";
  }

  draft.addEventListener("click", () => {
    if (!job.value.trim()) {
      status.textContent = "Write what the agent should do";
      return;
    }
    if (send({ type: "skill_draft", request: request(), description: job.value, examples: examples.value,
               ...(page.value ? { page_target: page.value } : {}) })) {
      status.textContent = "Drafting…";
    }
  });
  text.addEventListener("input", () => { name.textContent = nameOf(text.value); });
  save.addEventListener("click", () => {
    clearAnswers();
    send({ type: "skill_save", request: request(), text: text.value });
  });
  saveAs.addEventListener("click", () => {
    text.value = text.value.replace(/^name:.*$/m, `name: ${saveAs.dataset.name}`);
    name.textContent = nameOf(text.value);
    clearAnswers();
    send({ type: "skill_save", request: request(), text: text.value });
  });
  update.addEventListener("click", () => send({ type: "skill_save", request: request(), text: text.value, update: true }));
  confirm.addEventListener("click", () => {
    send({ type: "skill_save", request: request(), text: text.value, update: true, confirm: true });
  });
  tryIt.addEventListener("click", () => {
    if (!task.value.trim()) {
      result.textContent = "Write a test task first";
      return;
    }
    send({ type: "new_task", request: request(), skills: [], model: model(),
           text: `Follow this skill draft (not saved yet):\n\n${text.value}\n\nTest task: ${task.value.trim()}` });
    result.textContent = "Started an agent with the draft";
  });
  discard.addEventListener("click", () => {
    editor.hidden = true;
    text.value = "";
    clearAnswers();
  });
  pages();

  return {
    tabsChanged: pages,
    fromAgent(agentId, agentName) { // Save as skill, from a finished agent's chat
      if (send({ type: "skill_draft", request: request(), from_agent: agentId })) {
        status.textContent = `Drafting a skill from ${agentName || "the agent"}'s chat…`;
        root.scrollIntoView({ block: "start" });
      }
    },
    onMessage(message) {
      if (!pending || message.request !== pending) return;
      if (message.type === "skill_drafted") {
        editor.hidden = false;
        text.value = message.text;
        name.textContent = message.name || nameOf(message.text);
        status.textContent = "Read it, change what you like, then Save";
        clearAnswers();
      } else if (message.type === "skill_saved") {
        clearAnswers();
        result.textContent = `Saved ${message.name}: agents can load it now`;
      } else if (message.type === "skill_diff") {
        diff.textContent = message.diff || "No changes";
        diff.hidden = confirm.hidden = false;
      } else if (message.type === "error") {
        if (message.exists) {
          saveAs.dataset.name = message.suggest;
          saveAs.textContent = `Save as ${message.suggest}`;
          exists.hidden = false;
        }
        (editor.hidden ? status : result).textContent = message.text;
      }
    },
  };
}
