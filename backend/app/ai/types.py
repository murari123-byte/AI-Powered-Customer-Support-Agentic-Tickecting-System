from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    """The model asking to run one tool, e.g. search_knowledge_base(query="refund policy")."""

    name: str
    arguments: dict = {}


class ChatMessage(BaseModel):
    role: Role
    content: str
    # Only on assistant messages: the tools the model asked for in that turn.
    tool_calls: list[ToolCall] | None = None
    # Only on tool messages: which tool this result belongs to.
    tool_name: str | None = None


class LLMResponse(BaseModel):
    """One raw reply from a provider, plus the numbers we log for cost and latency."""

    content: str
    model: str
    tool_calls: list[ToolCall] = []  # empty = the model answered with text instead of asking for a tool
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int


class ProviderHealth(BaseModel):
    reachable: bool
    # model name -> is it downloaded / available on the provider
    models: dict[str, bool]
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.reachable and all(self.models.values())


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    """A validated model answer.

    `data` is already a Pydantic object, never raw text. `response` is the final LLM reply
    that produced it, and `attempts` counts how many tries it took (1 = first try).
    """

    data: T
    response: LLMResponse
    attempts: int
