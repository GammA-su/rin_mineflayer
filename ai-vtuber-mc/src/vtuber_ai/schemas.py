from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatGoalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    user: str | None = "local_user"


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission: str = "survive and progress toward beating Minecraft"
    max_steps: int = Field(default=1, ge=1, le=20)
    user: str = "agent"
    allow_autonomy: bool = False


class LLMRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None


class FullContextConfig(BaseModel):
    """Compact tick history sent from the stream runner for full/full-window context modes."""
    model_config = ConfigDict(extra="forbid")

    ticks: list[dict[str, Any]] = Field(default_factory=list)
    max_ticks: int = Field(default=1000, ge=1, le=10000)
    window_ticks: int = Field(default=200, ge=1, le=2000)
    include_raw_results: bool = False
    include_planner_debug: bool = False


class EpisodeSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_index: int = 1
    tick_range: list[int] = Field(default_factory=lambda: [1, 50])
    episode_ticks: list[dict[str, Any]] = Field(default_factory=list)
    last_status: dict[str, Any] | None = None
    milestones: dict[str, Any] | None = None
    llm: LLMRequestConfig | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key_env: str | None = None


class AgentTickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission: str = "Beat Minecraft while playing naturally and surviving."
    user: str = "AI_VTuber"
    planner: str = "hybrid"
    allow_autonomy: bool = False
    llm: LLMRequestConfig | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key_env: str | None = None
    context_mode: str = "compressed"
    full_context: FullContextConfig | None = None
    episode_memory: dict[str, Any] | None = None


class AgentLiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission: str = "Beat Minecraft while playing naturally and surviving."
    user: str = "AI_VTuber"
    planner: str = "hybrid"
    max_ticks: int = Field(default=10, ge=1, le=50)
    allow_autonomy: bool = False
    tick_delay_sec: float = Field(default=1.0, ge=0.0, le=30.0)
    stop_on_failure: bool = False
    llm: LLMRequestConfig | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key_env: str | None = None


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    speech: str = ""
    reason: str = ""


class BrainDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    speech: str = ""
    mood: str = "neutral"
    reason: str = ""


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    action: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
