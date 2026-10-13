from __future__ import annotations

import asyncio

from app.orchestrator.state_machine import TurnContext
from app.orchestrator.tts_stream import TTSSentenceStreamer
from speech.contracts import TTSChunk, TTSRequest


class _ThreeChunkAdapter:
    async def synthesize(self, request: TTSRequest, token):
        for index in range(3):
            token.raise_if_cancelled()
            yield TTSChunk(
                session_id=request.session_id,
                turn_id=request.turn_id,
                generation_id=request.generation_id,
                segment_id=0,
                chunk_id=index,
                text=request.segments[0],
                pcm_s16le=b"\x00\x00\x01\x00",
                sample_rate=24000,
                is_first_chunk=index == 0,
            )


def test_cancelled_context_does_not_yield_remaining_chunks(monkeypatch):
    context = TurnContext(turn_id="t1", session_id="s1", tenant_id="acme-it-demo")
    streamer = TTSSentenceStreamer("s1", "t1", context)
    adapter = _ThreeChunkAdapter()
    monkeypatch.setattr(
        "app.voice_agent.factory.get_tts_adapter_for_mode",
        lambda: adapter,
    )

    async def run() -> list:
        events = []
        agen = streamer._synthesize("Раз. Два.")
        first = await agen.__anext__()
        events.append(first)
        context.cancel()
        async for event in agen:
            events.append(event)
        return events

    events = asyncio.run(run())
    assert len(events) == 1
    assert events[0].generation_id == "t1"
