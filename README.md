# Job Application Agent

## Установка (1 минута)

```bash
pip install playwright openai
playwright install chromium
```

## Запуск Chrome с debug-портом

**Mac:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

**Windows** (в cmd, не PowerShell):
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**Linux:**
```bash
google-chrome --remote-debugging-port=9222
```

> В открывшемся Chrome **войдите в LinkedIn вручную** — сессия уже ваша.

## Конфиг (agent.py, строки 40-75)

1. `OPENAI_API_KEY` — ваш ключ
2. `ME = { ... }` — ваши данные (имя, email, телефон, опыт...)
3. `SEARCH_QUERY` / `LOCATION` — что ищем
4. `RESUME_PDF` — путь к вашему PDF резюме
5. `ONLY_EASY_APPLY = True` — только Easy Apply (безопаснее)

## Запуск

```bash
python agent.py
```

## Стоимость OpenAI

| Модель | Cover letter | Ответы на вопросы | Итого/заявка |
|--------|-------------|-------------------|--------------|
| gpt-4o-mini | ~$0.001 | ~$0.001 | **~$0.002** |
| gpt-4o | ~$0.008 | ~$0.004 | **~$0.012** |

50 заявок на gpt-4o-mini ≈ **$0.10** 🟢

## Файловая структура

```
agent.py          ← главный файл
resume.pdf        ← ваше резюме (обязательно!)
applied/          ← логи всех заявок (JSON)
  └ jobid_Company.json
```

## Антидетект

- Подключается к **вашему Chrome** (не создаёт новый) — никаких webdriver флагов
- Посимвольная печать с рандомными задержками
- Паузы 4–9 сек между заявками
- Использует вашу существующую LinkedIn сессию
