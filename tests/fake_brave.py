"""Test stand-ins: the user's Brave as the app sees it (app/bravelink.BraveLink), and an agent with no Claude Code
process behind it."""

from __future__ import annotations


class FakeBrave:
    """BraveLink's surface, holding the tabs a test gives it; owners, Watch, closes and connects are recorded."""

    name = "Brave"

    def __init__(self, pages=(), state="connected"):
        self.state = state
        self.pages = [dict(page) for page in pages]  # {"target", "url", "title"}
        self.owners: dict[str, dict] = {}
        self.watched, self.closed, self.marked = [], [], []
        self.connects = 0
        self._changes, self._states = [], []

    def on_change(self, callback):
        self._changes.append(callback)

    def on_state(self, callback):
        self._states.append(callback)

    def set_state(self, state):
        self.state = state
        for callback in list(self._states):
            callback(state)

    def tabs(self):
        return [{**page, "owner": dict(self.owners.get(page["target"], {"kind": "you"}))} for page in self.pages]

    def changed(self):
        for callback in list(self._changes):
            callback(self.tabs())

    def set_owner(self, target, owner):
        self.owners[target] = dict(owner)
        self.changed()

    def forget(self, target):
        self.owners.pop(target, None)
        self.changed()

    def release(self, owner_id):
        for target in [target for target, owner in self.owners.items() if owner.get("id") == owner_id]:
            del self.owners[target]
        self.changed()

    def mark_brain(self, url):
        self.marked.append(url)

    async def connect(self):
        self.connects += 1

    async def watch(self, target):
        self.watched.append(target)

    async def close_targets(self, targets):
        self.closed += list(targets)

    async def thumbnail(self, target):
        return None

    async def page_text(self, target, picked=False):
        return ""


class NoBridge:
    """An agent's bridge with no Claude Code process: each message ends its turn at once."""

    loaded_skills: set = set()
    model = "sonnet"

    async def send(self, text, tab_url="", tab_title="", skills=(), tab_label="panel"):
        yield {"type": "done", "seconds": 0, "cost": 0}

    async def stop(self):
        pass

    async def close(self):
        pass


def add_agent(manager, agent_id="a1", name="Fix the footer", color="blue", adopted=()):
    """An agent in the manager's list, as if started and done with its turn, with no process behind it."""
    from ai_browser.app.agents import Agent

    agent = Agent(agent_id, name, color, "sonnet", NoBridge(), state="your_turn")
    agent.adopted += list(adopted)
    manager.agents[agent_id] = agent
    return agent
