# IH AI szerver használata (Superset + Cursor)

Rövid üzemeltetői / fejlesztői útmutató ahhoz az AI infrastruktúrához, amit a Superset **Vambery AI Agent** extension használ.

## Mi van bekötve?

Két független LLM backend van a Superset oldalon (pdapp2 `.env-local`):

| Backend | Hol | Mire jó |
|---------|-----|---------|
| **Azure OpenAI** | `https://sandbox-ai-swedencentral.openai.azure.com/` | Cloud GPT (pl. `gpt-5.2-chat` deployment) |
| **Ollama (belső AI szerver)** | `http://aia08.inhat.hu:11434` | Saját / self-hosted modellek |

Alapértelmezett provider a Superset configban jelenleg: **`AI_PROVIDER=azure_openai`**.  
Az Ollama ennek ellenére **párhuzamosan** is elérhető: a chat UI model selector fel tudja sorolni mindkét provider modelljeit (`azure_openai/...`, `ollama/...`).

> Secrets (API key, Azure client secret) **nem** kerülnek ebbe a doksiba. Azok: `/docker/env-files/superset/.env-local` és a futó repo `docker/.env-local`.

---

## 1) Ollama AI szerver elérése

### Alap URL-ek

| Cél | URL |
|-----|-----|
| Ollama natív API | `http://aia08.inhat.hu:11434` |
| OpenAI-kompatibilis API | `http://aia08.inhat.hu:11434/v1` |
| Telepített modellek listája | `GET http://aia08.inhat.hu:11434/api/tags` |
| OpenAI-szerű model lista | `GET http://aia08.inhat.hu:11434/v1/models` |
| Chat (OpenAI formátum) | `POST http://aia08.inhat.hu:11434/v1/chat/completions` |

**Hálózat:** belső AD / IH hálózat (vagy VPN). Külső internetről általában **nem** érhető el. Auth alapból nincs (Ollama default) — ne tedd publikusra.

### Gyors ellenőrzés (PowerShell / bash)

```bash
curl http://aia08.inhat.hu:11434/api/tags
curl http://aia08.inhat.hu:11434/v1/models
```

### Egyszerű chat teszt (OpenAI-compatible)

```bash
curl http://aia08.inhat.hu:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-coder:30b",
    "messages": [{"role": "user", "content": "Mondj egy rövid hellót."}],
    "stream": false
  }'
```

### Jelenleg telepített modellek (pdapp2-ről ellenőrizve)

Chat / tool-capable példák:

- `qwen3.5:122b` — nagy, tool + vision + thinking (Superset default Ollama model)
- `gpt-oss:120b`
- `qwen3-next:80b`
- `gemma4:31b`
- `qwen3-coder:30b` — kódoláshoz jó kiindulás
- `qwen3-vl:32b` — vision
- `nemotron-3-nano:30b`
- `glm-4.7-flash:q8_0`
- `translategemma:27b`
- `glm-ocr:bf16`

Embedding:

- `nomic-embed-text:latest`
- `bge-m3:567m`
- `embeddinggemma:300m`
- `qwen3-embedding:8b`

A lista változik; mindig `GET /api/tags` a truth.

---

## 2) Hogyan használja a Superset?

A Vambery extension env-ből olvassa a provider configot (`docker/.env-local`):

```bash
# Default provider
AI_PROVIDER=azure_openai

# Azure
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://sandbox-ai-swedencentral.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-5.2-chat
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# Ollama (párhuzamosan felismerhető)
OLLAMA_BASE_URL=http://aia08.inhat.hu:11434
OLLAMA_MODEL=qwen3.5:122b
```

Használat a UI-ban:

1. Nyisd meg a Superset **SQL Lab**-ot.
2. Jobb oldali **Vambery AI Agent** panel.
3. Model dropdown: pl. `azure_openai/gpt-5.2-chat` vagy `ollama/qwen3.5:122b`.
4. Kérdezz / kérj SQL-t, chartot, stb.

API (Superset-en keresztül, bejelentkezés után):

- `GET /api/v1/ai_assistant/models`
- `POST /api/v1/ai_assistant/chat` / stream endpoint

Részletek: `ai_assistant/README.md`.

**Fontos:** a Vambery agent **tool-calling**ot vár. Nem minden Ollama model alkalmas rá jól. Preferáld a `tools` capability-s modelleket (pl. `qwen3.5:122b`, `qwen3-coder:30b`).

---

## 3) Cursor-ba bekötés (OpenAI-compatible override)

Az Ollama `/v1` endpoint OpenAI Chat Completions kompatibilis. Cursorban:

1. **Cursor Settings → Models**
2. **OpenAI API Key**: bármilyen nem üres string (pl. `ollama`) — Ollama nem ellenőrzi.
3. **Override OpenAI Base URL**:  
   `http://aia08.inhat.hu:11434/v1`
4. **Add model**: pontos név, ahogy az Ollama listázza, pl.:
   - `qwen3-coder:30b`
   - `qwen3.5:122b`
   - `gpt-oss:120b`
5. A model listában ideiglenesen **csak** a saját model legyen kijelölve (különben Cursor más cloud modelleket is próbálhat validálni).
6. Verify / próbachat.

### Tipikus buktatók

| Probléma | Ok / teendő |
|----------|-------------|
| Nem csatlakozik Cursorból | Laptop nincs IH hálón / VPN-en, vagy a Cursor cloud proxy **nem** látja a belső HTTP hostot |
| Cursor „public HTTPS” kell | Egyes Cursor verziók / Agent útvonalak a kérést a Cursor szerverein keresztül küldik — ekkor belső `http://aia08...` **nem** elég. Megoldás: belső reverse proxy + HTTPS, vagy tunnel (csak jóváhagyott módon) |
| Rossz model név | Pontosan egyezzen az `ollama list` / `/api/tags` névvel (`tag` is számít) |
| Lassú válasz | Nagy model (122B) GPU foglalt; próbálj kisebbet (`qwen3-coder:30b`) |
| Agent / tool gyenge | Válts tool-capable, nagyobb modellre |

**Chat / Cmd+K** általában átirányítható custom endpointre.  
**Tab autocomplete** gyakran Cursor cloud-only marad — ne számíts rá helyi Ollamával.

### Alternatíva Cursor helyett (ha az override nem működik)

Ugyanarra az URL-re köthető:

- Continue.dev / Cline / Open WebUI
- Bármilyen OpenAI SDK kliens `base_url=http://aia08.inhat.hu:11434/v1` + dummy API key

Példa Python:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://aia08.inhat.hu:11434/v1",
    api_key="ollama",
)
resp = client.chat.completions.create(
    model="qwen3-coder:30b",
    messages=[{"role": "user", "content": "Írj egy hello world Python függvényt"}],
)
print(resp.choices[0].message.content)
```

---

## 4) Tudunk-e saját új modellt tenni rá?

**Igen.** Ez Ollama szerver — új model = `ollama pull` (vagy saját GGUF import) a **aia08** gépen, megfelelő jogosultsággal.

### Új modell telepítése (üzemeltető / AI host admin)

SSH aia08-ra (vagy ahova az Ollama telepítve van), majd:

```bash
# Példa: hivatalos Ollama registry-ből
ollama pull qwen2.5-coder:32b

# Ellenőrzés
ollama list
curl http://127.0.0.1:11434/api/tags
```

Saját / privát GGUF:

```bash
# Modelfile példa
# FROM ./my-model.gguf
# PARAMETER temperature 0.2
ollama create my-custom-model -f Modelfile
```

Utána:

1. **Cursor**: Add Model → `my-custom-model` (vagy a teljes tag név).
2. **Superset Vambery**: a model listát az extension dinamikusan kérdezi (`/api/tags`). Újraindítás általában **nem** kell; ha cache / UI sticky, frissítsd az oldalt. Default model váltáshoz:

```bash
OLLAMA_MODEL=my-custom-model
```

és Superset restart (ha a defaultot is át akarod állítani).

### Mit érdemes feltenni?

| Use case | Ajánlás |
|----------|---------|
| Superset agent (SQL + tools) | Tool-calling + min. ~30B, ideálisan 70B+ |
| Cursor kódolás | `*-coder*` család, 30B környék |
| Gyors / olcsó próbák | kisebb 7–14B (ha van), vagy flash modellek |
| Embedding / RAG | `bge-m3`, `nomic-embed-text`, `qwen3-embedding` |
| Vision / OCR | `qwen3-vl`, `glm-ocr` |

VRAM / GPU limit: nagy modellek (80B–122B) egymással ütközhetnek — egyidejű terhelésnél várakozás vagy OOM lehet.

---

## 5) Azure OpenAI oldal (röviden)

- Endpoint: `https://sandbox-ai-swedencentral.openai.azure.com/`
- Deployment példa: `gpt-5.2-chat`
- Auth: `AZURE_OPENAI_API_KEY` (env)
- Cursorba Azure-t külön Azure OpenAI / custom base URL módon lehet kötni, de az **API key** kell — ezt ne másold doksiba / chatbe. Éles / sandbox policy szerint kérj kulcsot.

---

## 6) Checklist üzemeltetőnek / fejlesztőnek

- [ ] VPN / belső hálózat OK → `curl aia08:11434/api/tags` megy
- [ ] Kell-e új model? → `ollama pull` / `ollama create` aia08-on
- [ ] Superset: `.env-local` tartalmazza `OLLAMA_BASE_URL` (+ opcionálisan `OLLAMA_MODEL`)
- [ ] UI-ban megjelenik `ollama/<model>` a dropdownban
- [ ] Cursor: Base URL `.../v1`, model név pontos, csak az a model legyen aktív
- [ ] Ha Cursor nem látja a belső HTTP-t → ne publikus ngrok ad-hoc; egyeztess reverse proxy / HTTPS megoldást

---

## Kapcsolódó fájlok

- Extension config mapping: `ai_assistant/backend/src/ai_assistant/config.py`
- Teljes Vambery README: `ai_assistant/README.md`
- Futó env (pdapp2): `/docker/github-repo/superset/docker/.env-local`  
  (backup secrets: `/docker/env-files/superset/.env-local`)
