"""The Brain's account (AI accounts Decision 10): every one-shot Claude call of the Brain and its skill writer runs on
the account chosen in Settings → Accounts → The Brain's account.

A call refused at a usage limit marks that account, and the app shows the Brain's card in AI Home ("The Brain hit its
limit on Personal. Continue on Work?"). The call then waits, for the rest of its own time limit, for the user's click:
the click sets the Brain's account, and the call runs once more there. Without a click in that time, it ends with
"<name> hit its usage limit". Nothing switches without the click."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from ..limits import from_text
from .oneshot import OneShot, ask_claude

LIMIT_ERROR = "{name} hit its usage limit"


class BrainAccount:
    """Called like ask_claude, by BrainService and SkillWriter (their `ask`)."""

    def __init__(self, accounts, ask=ask_claude):
        self.accounts = accounts
        self.ask = ask
        self.on_limit: Callable[[dict], None] = lambda limit: None  # the app shows the card: {"account", "resets_at"}
        self._switched = asyncio.Event()

    def switched(self) -> None:
        """The Brain's account changed (the card's click, or Settings): calls waiting at a limit run once more."""
        event, self._switched = self._switched, asyncio.Event()
        event.set()

    async def __call__(self, prompt: str, model: str = "haiku", claude=None, cwd=None, timeout: float = 120,
                       think: bool = False) -> OneShot:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        account = self.accounts.brain_id()
        answer, limited = await self._once(account, prompt, model, claude, cwd, timeout, think)
        while limited and self.accounts.brain_id() == account:  # the click, for the rest of this call's time
            left = deadline - loop.time()
            if left <= 0:
                return answer
            try:
                await asyncio.wait_for(self._switched.wait(), left)
            except TimeoutError:
                return answer
        if not limited:
            return answer
        retried, _ = await self._once(self.accounts.brain_id(), prompt, model, claude, cwd, timeout, think)  # once
        return retried

    async def _once(self, account: str, prompt: str, model: str, claude, cwd, timeout: float,
                    think: bool) -> tuple[OneShot, bool]:
        answer = await self.ask(prompt, model=model, claude=claude, cwd=cwd, timeout=timeout, think=think,
                                env=self.accounts.env_for(account))
        hit = from_text(answer.error) if answer.error else None
        if hit is None:
            return answer, False
        self.accounts.set_limit(account, hit.resets_at)
        self.on_limit({"account": account, "resets_at": hit.resets_at})
        named = self.accounts.get(account)
        return OneShot(cost=answer.cost,
                       error=LIMIT_ERROR.format(name=named.name if named is not None else "The Brain's account")), True
