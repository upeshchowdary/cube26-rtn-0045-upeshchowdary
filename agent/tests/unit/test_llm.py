"""P5 model-layer tests without spending quota.

They cover schema export, prompt locking, SDK retries, provider errors, pricing, replay,
context assembly, exception tools, and the stateful session loop.
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from returns_manager.config import get_settings
from returns_manager.errors import QuotaExhaustedError, VerificationFailed
from returns_manager.llm import prompts as prompts_mod
from returns_manager.llm.client import (
    ModelRequest,
    ModelResponse,
    ProviderError,
    SafetyBlockedError,
    SchemaError,
    TruncatedError,
    response_from_raw,
)
from returns_manager.llm.context import ReturnPhoto, assemble
from returns_manager.llm.gemini_client import build_sdk_client, classify_provider_exception
from returns_manager.llm.loop import SessionFailed, run_session
from returns_manager.llm.pricing import cost_usd_micros
from returns_manager.llm.replay_client import (
    CassetteMismatch,
    RecordingModelClient,
    ReplayModelClient,
    request_fingerprint,
)
from returns_manager.llm.schemas import JudgmentV1, gemini_response_schema, schema_depth
from returns_manager.llm.tools import BUDGET_EXHAUSTED, tool_definitions
from tests.unit import judgment_builders as b

SUPPORTED = {
    "type",
    "title",
    "description",
    "enum",
    "format",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "prefixItems",
    "minItems",
    "maxItems",
}


# ── schema ────────────────────────────────────────────────────────────────
def _keys(node: Any, out: set[str]) -> set[str]:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "properties":
                for sub in v.values():
                    _keys(sub, out)
            else:
                out.add(k)
                _keys(v, out)
    elif isinstance(node, list):
        for x in node:
            _keys(x, out)
    return out


def test_gemini_schema_is_flat_supported_and_has_no_disposition() -> None:
    s = gemini_response_schema()
    text = json.dumps(s)
    assert "$defs" not in text
    assert "$ref" not in text
    assert _keys(s, set()) <= SUPPORTED
    assert schema_depth(s) <= 3
    assert "disposition" not in text
    assert set(s["required"]) == set(JudgmentV1.model_fields)


def test_judgment_ranges_are_checked_in_code() -> None:
    ctx = b.context(b.card("org_demo_alpha", "SKU-LAMP-LED"))
    good = b.judgment(ctx).model_dump()
    bad_conf = json.loads(json.dumps(good))
    bad_conf["identity"]["confidence"] = 1.2
    bad_box = json.loads(json.dumps(good))
    bad_box["identity"]["evidence"][0]["box_2d"] = [600, 100, 500, 900]
    for data in (bad_conf, bad_box):
        with pytest.raises(ValueError, match=r"confidence|box_2d"):
            JudgmentV1.model_validate(data)


# ── prompts ───────────────────────────────────────────────────────────────
def test_prompt_lock_holds_for_the_committed_prompts() -> None:
    locked = prompts_mod.verify_lock()
    assert {"judgment", "judgment_task"} <= set(locked)
    for p in locked.values():
        assert "2026" not in p.body, "no dates in prompts (cache stability)"


def test_prompt_change_without_version_bump_fails(tmp_path: Path) -> None:
    d = tmp_path / "prompts" / "judgment"
    d.mkdir(parents=True)
    f = d / "system.md"
    f.write_text("---\nprompt_id: judgment\nversion: 1.0.0\nsummary: s\n---\nbody\n", encoding="utf-8")
    lock = tmp_path / "prompts" / "prompts.lock.json"
    prompts_mod.write_lock(tmp_path / "prompts", lock)
    prompts_mod.verify_lock(tmp_path / "prompts", lock)
    f.write_text(
        "---\nprompt_id: judgment\nversion: 1.0.0\nsummary: s\n---\nbody changed\n", encoding="utf-8"
    )
    with pytest.raises(VerificationFailed, match="without a version bump"):
        prompts_mod.verify_lock(tmp_path / "prompts", lock)
    f.write_text(
        "---\nprompt_id: judgment\nversion: 1.0.1\nsummary: s\n---\nbody changed\n", encoding="utf-8"
    )
    with pytest.raises(VerificationFailed, match="lock was not updated"):
        prompts_mod.verify_lock(tmp_path / "prompts", lock)


# ── SDK client configuration (finding F-011) ──────────────────────────────
def test_sdk_automatic_retries_are_off() -> None:
    client = build_sdk_client("not-a-real-key", 180)
    for resource in (client.interactions, client.aio.interactions):
        assert resource.sdk_configuration.retry_config is None
        assert resource.sdk_configuration.timeout_ms == 180_000


@dataclass
class _FakeHttpError(Exception):
    status_code: int
    message: str
    body: Any = None

    def __str__(self) -> str:
        return self.message


@pytest.mark.parametrize(
    ("exc", "cls"),
    [
        (
            _FakeHttpError(
                429,
                "Quota exceeded",
                {"error": {"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}},
            ),
            "quota_exhausted",
        ),
        (
            _FakeHttpError(429, "Resource exhausted", {"error": {"details": [{"retryDelay": "17s"}]}}),
            "rate_limit",
        ),
        (_FakeHttpError(503, "The model is overloaded"), "server_error"),
        (_FakeHttpError(400, "Invalid JSON payload"), "invalid_request"),
        (_FakeHttpError(403, "Permission denied"), "auth"),
        (_FakeHttpError(404, "models/x is not found"), "not_found"),
        (TimeoutError("read timeout"), "timeout"),
        (ConnectionError("reset"), "network"),
    ],
)
def test_provider_errors_map_to_section_10_4_classes(exc: Exception, cls: str) -> None:
    err = classify_provider_exception(exc)
    assert err.error_class == cls
    if cls == "rate_limit":
        assert err.retry_after_s == 17.0


# ── pricing ───────────────────────────────────────────────────────────────
def test_paid_equivalent_cost_method() -> None:
    usage = {
        "total_input_tokens": 10_000,
        "total_cached_tokens": 4_000,
        "total_output_tokens": 1_000,
        "total_thought_tokens": 500,
    }
    # (6000 x 0.75) + (4000 x 0.075) + (1500 x 3.75) micro-USD = 4500 + 300 + 5625
    assert cost_usd_micros("gemini-3.8-flash", usage) == 10_425
    assert cost_usd_micros("no-such-model", usage) is None


# ── replay cassettes ──────────────────────────────────────────────────────
def _req(text: str = "hello", image: bytes = b"img", previous: str | None = None) -> ModelRequest:
    return ModelRequest(
        model="m",
        system_instruction="sys",
        tools=[],
        generation_config={"thinking_level": "low"},
        response_format=None,
        previous_interaction_id=previous,
        input=[
            {"type": "text", "text": text},
            {"type": "image", "data": base64.b64encode(image).decode(), "mime_type": "image/jpeg"},
        ],
    )


def _raw(
    text: str, status: str = "completed", calls: list[dict[str, Any]] | None = None, iid: str = "int-1"
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [{"type": "function_call", **c} for c in (calls or [])]
    if text:
        steps.append({"type": "model_output", "content": [{"type": "text", "text": text}]})
    return {
        "id": iid,
        "status": status,
        "steps": steps,
        "usage": {
            "total_input_tokens": 5000,
            "total_output_tokens": 800,
            "total_cached_tokens": 0,
            "total_thought_tokens": 300,
        },
    }


def test_fingerprint_ignores_server_ids_but_not_content() -> None:
    assert request_fingerprint(_req()) == request_fingerprint(_req(previous="int-9"))
    assert request_fingerprint(_req()) != request_fingerprint(_req(text="changed"))
    assert request_fingerprint(_req()) != request_fingerprint(_req(image=b"other"))


async def test_record_then_replay_and_mismatch_fails_loudly(tmp_path: Path) -> None:
    class Live:
        async def create(self, request: ModelRequest) -> ModelResponse:
            return response_from_raw(_raw('{"ok": true}'), 42)

    cassette = tmp_path / "c.jsonl"
    await RecordingModelClient(Live(), cassette).create(_req())
    line = json.loads(cassette.read_text(encoding="utf-8"))
    assert line["request_summary"]["images"] == 1
    assert "img" not in json.dumps(line["request_summary"])
    replay = ReplayModelClient(cassette)
    assert (await replay.create(_req())).output_text == '{"ok": true}'
    with pytest.raises(CassetteMismatch, match="not in the cassette"):
        await replay.create(_req())
    with pytest.raises(CassetteMismatch, match="request changed"):
        await ReplayModelClient(cassette).create(_req(text="edited prompt"))


# ── context assembly ──────────────────────────────────────────────────────
def _jpeg(seed: int, size: tuple[int, int] = (1200, 900)) -> bytes:
    rng = np.random.default_rng(seed)
    blocks = rng.integers(40, 220, size=(size[1] // 50, size[0] // 50, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(np.kron(blocks, np.ones((50, 50, 1), dtype=np.uint8)), "RGB").save(buf, "JPEG")
    return buf.getvalue()


def _photos(seed: int) -> list[ReturnPhoto]:
    return [
        ReturnPhoto(f"P{i}", f"ph{seed}{i}", "a" * 64, _jpeg(seed + i), _jpeg(seed + i), "pass", (), ())
        for i in (1, 2)
    ]


def _bundle(seed: int, *, settings: Any = None) -> Any:
    card = b.card("org_demo_alpha", "SKU-LAMP-LED")
    ctx = b.context(card)
    return assemble(
        settings=settings or get_settings(),
        return_row={"return_id": f"r{seed}", "order_id": f"ORD-{seed}"},
        card=card,
        other_cards={},
        rubric=ctx.rubric,
        policy=ctx.policy,
        photos=_photos(seed),
        refs=[
            ("ref_front", "front", "b" * 64, _jpeg(99)),
            ("ref_back", "back", "c" * 64, _jpeg(98)),
            ("ref_label", "label", "d" * 64, _jpeg(97)),
        ],
    )


def test_sku_block_is_byte_identical_across_returns_of_the_same_sku() -> None:
    a, c = _bundle(1), _bundle(2)
    assert a.sku_block == c.sku_block
    assert a.sku_block_sha256() == c.sku_block_sha256()
    assert a.unit_block != c.unit_block
    assert a.input_items()[: len(a.sku_block)] == a.sku_block  # stable prefix first


def test_context_is_blind_and_uses_aliases() -> None:
    bundle = _bundle(3)
    texts = " ".join(i.get("text", "") for i in bundle.input_items())
    assert "operator" not in texts.lower()
    assert "list_price" not in texts
    assert "amount_minor" not in texts
    assert [r.alias for r in bundle.references] == ["R1", "R2", "R3"]
    assert bundle.initial_reference_aliases == ("R1", "R2")  # at most two references up front
    assert sum(1 for i in bundle.input_items() if i["type"] == "image") == 2 + 2
    task_index = next(i for i, x in enumerate(bundle.input_items()) if x.get("text", "").startswith("TASK"))
    photo_index = next(
        i for i, x in enumerate(bundle.input_items()) if x.get("text", "").startswith("RETURN PHOTOS")
    )
    assert task_index < photo_index  # instruction before the photos


# ── session loop against a scripted client ────────────────────────────────
@dataclass
class ScriptedClient:
    responses: list[dict[str, Any]]
    requests: list[ModelRequest] = field(default_factory=list)

    async def create(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        raw = self.responses.pop(0)
        if "raise" in raw:
            raise raw["raise"]
        return response_from_raw(raw, 1000)


@dataclass
class FakeQuota:
    remaining: int = 10
    taken: int = 0
    released: int = 0
    exhausted: list[str] = field(default_factory=list)

    @asynccontextmanager
    async def reserve(self, model_id: str, role: str, n: int) -> AsyncIterator[Any]:
        if n > self.remaining:
            raise QuotaExhaustedError("budget cannot cover the session")
        self.remaining -= n
        fake = self

        class R:
            used = 0

            async def take(self) -> None:
                if self.used >= n:
                    raise QuotaExhaustedError("over reservation")
                self.used += 1
                fake.taken += 1

        r = R()
        try:
            yield r
        finally:
            fake.released += n - r.used
            fake.remaining += n - r.used

    async def mark_exhausted(self, model_id: str, role: str) -> None:
        self.exhausted.append(model_id)


def _valid_output() -> str:
    ctx = b.context(b.card("org_demo_alpha", "SKU-LAMP-LED"))
    return b.judgment(ctx).model_dump_json()


async def test_t_rpl_one_request_when_no_tools_needed() -> None:
    client, quota = ScriptedClient([_raw(_valid_output())]), FakeQuota()
    result = await run_session(client, quota, _bundle(4), get_settings())  # type: ignore[arg-type]
    assert len(client.requests) == 1
    assert quota.taken == 1
    assert quota.released == get_settings().rm_max_round_trips - 1
    req = client.requests[0]
    assert "temperature" not in json.dumps(req.generation_config)
    assert req.generation_config["tool_choice"] == {"allowed_tools": {"mode": "auto"}}
    assert req.response_format is not None
    assert result.trace.usage["total_input_tokens"] == 5000


async def test_t_rpl_parallel_tool_calls_answered_in_one_chained_turn() -> None:
    calls = [
        {
            "id": "c1",
            "name": "crop_photo_region",
            "arguments": {"photo": "P1", "box_2d": [100, 100, 500, 500], "purpose": "read_label"},
        },
        {
            "id": "c2",
            "name": "crop_photo_region",
            "arguments": {"photo": "P2", "box_2d": [0, 0, 1000, 1000], "purpose": "inspect_damage"},
        },
    ]
    client = ScriptedClient(
        [_raw("", "requires_action", calls, iid="int-A"), _raw(_valid_output(), iid="int-B")]
    )
    result = await run_session(client, FakeQuota(), _bundle(5), get_settings())  # type: ignore[arg-type]
    first, second = client.requests
    assert second.previous_interaction_id == "int-A"
    assert [s["type"] for s in second.input] == ["function_result", "function_result"]
    assert [s["call_id"] for s in second.input] == ["c1", "c2"]
    assert all(any(x["type"] == "image" for x in s["result"]) for s in second.input)
    assert (second.tools, second.generation_config, second.response_format, second.system_instruction) == (
        first.tools,
        first.generation_config,
        first.response_format,
        first.system_instruction,
    )
    assert result.crop_aliases == ("C1", "C2")
    assert len(result.trace.tools) == 2


async def test_t_rpl_round_trip_budget_enforced() -> None:
    call = [
        {
            "id": "c1",
            "name": "crop_photo_region",
            "arguments": {"photo": "P1", "box_2d": [0, 0, 10, 10], "purpose": "read_label"},
        }
    ]
    client = ScriptedClient([_raw("", "requires_action", call), _raw("", "requires_action", call)])
    with pytest.raises(SessionFailed) as info:
        await run_session(client, FakeQuota(), _bundle(6), get_settings())  # type: ignore[arg-type]
    assert isinstance(info.value.cause, SchemaError)
    assert len(client.requests) == get_settings().rm_max_round_trips
    assert len(info.value.trace.requests) == 2  # the partial trace is kept for the inspection record


@pytest.mark.parametrize(
    ("raw", "err"),
    [
        (_raw("", "incomplete"), TruncatedError),
        (
            {
                "id": "x",
                "status": "failed",
                "steps": [],
                "errors": [{"message": "Response blocked by safety filters"}],
            },
            SafetyBlockedError,
        ),
        (_raw("this is not json"), SchemaError),
        (_raw('{"schema_version": "judgment/v1"}'), SchemaError),
    ],
)
async def test_t_rpl_bad_endings_are_typed_errors(raw: dict[str, Any], err: type[Exception]) -> None:
    with pytest.raises(SessionFailed) as info:
        await run_session(ScriptedClient([raw]), FakeQuota(), _bundle(7), get_settings())  # type: ignore[arg-type]
    assert isinstance(info.value.cause, err)


async def test_t_rpl_no_request_when_the_budget_cannot_cover_the_session() -> None:
    client = ScriptedClient([_raw(_valid_output())])
    with pytest.raises(SessionFailed) as info:
        await run_session(client, FakeQuota(remaining=1), _bundle(8), get_settings())  # type: ignore[arg-type]
    assert isinstance(info.value.cause, QuotaExhaustedError)
    assert client.requests == []


async def test_t_rpl_daily_429_marks_the_model_exhausted() -> None:
    quota = FakeQuota()
    client = ScriptedClient([{"raise": ProviderError("quota_exhausted", "daily", status_code=429)}])
    with pytest.raises(SessionFailed):
        await run_session(client, quota, _bundle(9), get_settings())  # type: ignore[arg-type]
    assert quota.exhausted == [get_settings().rm_judgment_model]


async def test_t_rpl_json_prompted_gets_one_repair_turn() -> None:
    settings = get_settings().model_copy(update={"rm_output_mode": "json_prompted"})
    client = ScriptedClient(
        [_raw("{broken", iid="int-1"), _raw("```json\n" + _valid_output() + "\n```", iid="int-2")]
    )
    result = await run_session(client, FakeQuota(), _bundle(10, settings=settings), settings)  # type: ignore[arg-type]
    assert client.requests[0].response_format is None
    assert client.requests[1].previous_interaction_id == "int-1"
    assert result.judgment.schema_version == "judgment/v1"


def test_tools_are_sorted_read_only_and_crop_budget_is_enforced() -> None:
    names = [t["name"] for t in tool_definitions()]
    assert names == sorted(names) == ["crop_photo_region", "get_reference_views", "get_sibling_product"]
    from returns_manager.llm.client import FunctionCall
    from returns_manager.llm.tools import ToolExecutor

    ex = ToolExecutor(
        bundle=_bundle(11), settings=get_settings(), crop_budget=1, crop_resolution="ultra_high"
    )
    steps = ex.execute_all(
        [
            FunctionCall(
                "a", "crop_photo_region", {"photo": "P1", "box_2d": [0, 0, 500, 500], "purpose": "read_label"}
            ),
            FunctionCall(
                "b", "crop_photo_region", {"photo": "P1", "box_2d": [0, 0, 500, 500], "purpose": "read_label"}
            ),
            FunctionCall("c", "get_sibling_product", {"sku": "NOT-A-SIBLING"}),
        ],
        round_trip=1,
    )
    crop = Image.open(io.BytesIO(base64.b64decode(steps[0]["result"][1]["data"])))
    assert crop.size == (600, 450)  # half of the 1200x900 original, from the original bytes
    assert BUDGET_EXHAUSTED in steps[1]["result"][0]["text"]
    assert steps[2]["is_error"] is True
    assert [r.status for r in ex.records] == ["ok", "budget_exhausted", "error"]
