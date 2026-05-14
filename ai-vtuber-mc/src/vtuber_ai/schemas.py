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


class AgentTickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission: str = "Beat Minecraft while playing naturally and surviving."
    user: str = "AI_VTuber"
    planner: str = "hybrid"
    allow_autonomy: bool = False


class AgentLiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission: str = "Beat Minecraft while playing naturally and surviving."
    user: str = "AI_VTuber"
    planner: str = "hybrid"
    max_ticks: int = Field(default=10, ge=1, le=50)
    allow_autonomy: bool = False
    tick_delay_sec: float = Field(default=1.0, ge=0.0, le=30.0)


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
