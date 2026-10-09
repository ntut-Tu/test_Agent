"""Structured model responses; names preserve the existing wire schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class _PrSummary(BaseModel):
    summary: str


class _Line(BaseModel):
    path: str
    number: int
    reason: str


class _UncoveredLines(BaseModel):
    lines: list[_Line] = Field(default_factory=list)


class _TestSelection(BaseModel):
    focal_id: str
    test_id: str
    reason: str


class _ExistingTests(BaseModel):
    selections: list[_TestSelection] = Field(default_factory=list)
