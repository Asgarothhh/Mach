import asyncio
import httpx
import websockets
import json
import uuid
import time

API_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"


async def run_smoke_test():
    print("🚀 Запуск E2E Smoke Test...")

    # 1. Создаем сессию через REST API
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/v1/sessions",
            json={"tenant_id": "demo-tenant-1", "channel": "test-script"}
        )
        response.raise_for_status()
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"✅ Сессия создана: {session_id}")

    # 2. Подключаемся по WebSocket
    ws_endpoint = f"{WS_URL}/api/v1/ws/sessions/{session_id}"
    print(f"🔌 Подключение к {ws_endpoint}...")

    async with websockets.connect(ws_endpoint) as websocket:
        print("✅ WebSocket подключен")

        # 3. Эмулируем финальное распознавание (ASR Event)
        turn_id = str(uuid.uuid4())
        asr_event = {
            "type": "ASREvent",
            "payload": {
                "session_id": session_id,
                "turn_id": turn_id,
                "timestamp_ms": int(time.time() * 1000),
                "revision": 1,
                "text": "Сколько стоит роуминг в Турции?",
                "is_final": True,
                "language": "ru",
                "confidence": 0.98
            }
        }

        print(f"🗣️ Отправляем текст: '{asr_event['payload']['text']}'")
        await websocket.send(json.dumps(asr_event))

        # Ждем немного, чтобы бэкенд успел залогировать и обработать
        await asyncio.sleep(2)
        print("✅ Событие отправлено. Проверь логи бэкенда (docker logs)!")

        # 4. Завершаем сессию
        async with httpx.AsyncClient() as client:
            end_response = await client.post(f"{API_URL}/api/v1/sessions/{session_id}/end")
            end_response.raise_for_status()
            print("✅ Сессия успешно завершена")


if __name__ == "__main__":
    # Для запуска потребуется установить httpx и websockets:
    # pip install httpx websockets
    asyncio.run(run_smoke_test())