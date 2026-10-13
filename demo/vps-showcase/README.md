# VPS showcase (ML progress pages)

Статические страницы для команды, публикуются на VPS (Caddy, sslip.io).
VPS — только домен/раздача; тяжёлые вычисления (модели, синтез, бенчмарки)
выполняются на демо-машине.

## Deployment

```bash
# 1) собрать свежие страницы и аудио локально
.venv/bin/python scripts/tts_smoke.py --model-path models/tts/v5_5_ru.pt \
    --sample-rate 48000 --out artifacts/tts_48k
.venv/bin/python scripts/tts_ab_eval.py --out artifacts/tts_ab \
    --html demo/vps-showcase/tts-ab.html

# 2) выложить на VPS
ssh kametera 'mkdir -p /srv/mach-demo/audio /srv/mach-demo/tts_ab'
scp artifacts/vps-demo/index.html kametera:/srv/mach-demo/index.html
scp artifacts/tts_48k/segment_*.wav kametera:/srv/mach-demo/audio/
scp -r artifacts/tts_ab/* kametera:/srv/mach-demo/tts_ab/
scp demo/vps-showcase/tts-ab.html kametera:/srv/mach-demo/tts-ab.html
ssh kametera 'chmod -R a+rX /srv/mach-demo'
```

Caddy (на VPS): `mach.194-146-38-78.sslip.io` → `root /srv/mach-demo`,
`file_server` (см. `/etc/caddy/Caddyfile`, бэкап рядом).

## URLs

- https://mach.194-146-38-78.sslip.io/ — ML stage 0: сэмплы Silero v5, метрики.
- https://mach.194-146-38-78.sslip.io/tts-ab.html — A/B всех кандидатов на
  замену Silero (лицензии, first-chunk, RTF, WER, MOS) для прослушивания командой.
- **https://tts.194-146-38-78.sslip.io/** — живой TTS-полигон: ввод фразы и
  выбор голоса. Синтез выполняется на демо-машине (systemd user unit
  `tts-playground`, слушает `100.64.0.4:8077`); VPS только проксирует:
  `tts.194-146-38-78.sslip.io → reverse_proxy 100.64.0.4:8077` (см. Caddyfile).

## Notes

- Все аудио — синтетическая речь, персональных данных нет.
- Голос Silero v5_5_ru помечен как demo-only (CC BY-NC-SA) — это указано на странице.
- Для будущего живого демо полного агента: Caddy на VPS может делать
  `reverse_proxy` на демо-машину по Tailscale (100.64.0.4) без вычислений на VPS.
