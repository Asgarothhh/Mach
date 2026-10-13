# VPS showcase (ML progress page)

Статическая страница для команды, публикуется на VPS (Caddy, sslip.io):

```bash
# audio samples are regenerated locally, not committed
.venv/bin/python scripts/tts_smoke.py --model-path models/tts/v5_5_ru.pt \
    --sample-rate 48000 --out artifacts/tts_48k
mkdir -p /srv/mach-demo/audio
scp artifacts/vps-demo/index.html <vps>:/srv/mach-demo/index.html
scp artifacts/tts_48k/segment_*.wav <vps>:/srv/mach-demo/audio/
# Caddy site: mach.194-146-38-78.sslip.io -> root /srv/mach-demo, file_server
```

Живая версия: https://mach.194-146-38-78.sslip.io/
Страница обновляется вручную; объём статический (1 vCPU/1 ГБ RAM на VPS).

