"""Pydantic schemas for HalloPetra webhook API payloads."""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class HalloPetraMessage(BaseModel):
    # 'forbid' here: messages are tightly typed (role/content only); unknown
    # fields indicate a schema mismatch that should fail loudly.
    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant", "user"]
    content: str = Field(max_length=10_000)


class HalloPetraContactData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=32)
    email: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)


class HalloPetraCallData(BaseModel):
    # 'ignore' at vendor-level: tolerate added fields from the provider
    # without breaking our webhook receiver.
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=64)
    duration: int = Field(ge=0, le=86400)
    phone: Optional[str] = Field(default=None, max_length=32)
    topic: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = Field(default=None, max_length=5_000)
    messages: List[HalloPetraMessage] = Field(default_factory=list, max_length=500)
    collected_data: dict[str, Any] = Field(default_factory=dict)
    contact_data: Optional[HalloPetraContactData] = None
    main_task_id: Optional[str] = None
    email_send_to: Optional[str] = Field(default=None, max_length=255)
    forwarded_to: Optional[str] = None
    previous_webhook_calls: List[Any] = Field(default_factory=list)


class HalloPetraWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    webhook_id: str = Field(min_length=1, max_length=128)
    data: HalloPetraCallData
