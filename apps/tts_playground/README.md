# TTS-полигон (live-демо для команды)

Вводишь фразу, выбираешь движок и голос — получаешь аудио. Плюс вторая вкладка:
запись с микрофона или загрузка аудио → live-распознавание (T-one / GigaAM v3).
Синтез и распознавание крутятся на демо-машине (GPU/CPU); публичный адрес даёт
VPS через Caddy-reverse-proxy на Tailscale. Это инструмент тестирования
ML-трека, не часть call path.

Публичный адрес: **https://tts.194-146-38-78.sslip.io/**

## Движки

| Ключ | Лицензия | Голоса | Примечание |
|---|---|---|---|
| `silero-mit` | MIT + MIT (stress) | `ru_ekaterina`, `ru_saida`, `ru_bogdan` (шортлист) | рекомендованный production-кандидат |
| `silero-v5` | CC BY-NC-SA (демо) | xenia, baya, kseniya, aidar, eugene | эталон качества, интонация вопросов (`*слово*`) |
| `kokoro-ru` | OpenRAIL (GPL-3 в G2P) | sveta, masha, dima | лучшая разборчивость, CPU |
| `chatterbox` | MIT | встроенный голос | GPU, экспериментальный |

## Локальный запуск

```bash
.venv/bin/python apps/tts_playground/server.py --host 127.0.0.1 --port 8077
# открыть http://127.0.0.1:8077
```

Модели грузятся лениво при первом обращении к движку (с прогревом);
первый запрос к новому движку может занять до ~60 секунд.

## Постоянный сервис (systemd user)

```bash
cp apps/tts_playground/tts-playground.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tts-playground
systemctl --user status tts-playground
```

Юнит слушает только Tailscale-адрес (`100.64.0.4:8077`) — наружу не выставлен.

## Публикация через VPS (Caddy)

На VPS добавлен сайт (см. `/etc/caddy/Caddyfile`):

```
tts.194-146-38-78.sslip.io {
	encode gzip zstd
	reverse_proxy 100.64.0.4:8077 {
		flush_interval -1
		transport http {
			read_timeout 0
			write_timeout 0
			dial_timeout 10s
		}
	}
}
```

## Ограничения и безопасность

- текст до 300 символов; аудио до 25 МБ / 60 секунд; 30 запросов/мин на IP;
  синтез и распознавание сериализуются;
- текст не логируется и никуда не отправляется — только локальные модели;
- распознавание: `POST /api/transcribe` (multipart: `file`, `engine=t-one|gigaam-v3-ctc`),
  список движков — `GET /api/asr-engines`;
- сервис не имеет доступа к данным звонков, БД или внешним API.
