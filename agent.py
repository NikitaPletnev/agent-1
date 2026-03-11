"""
╔══════════════════════════════════════════════════════════╗
║        JOB APPLICATION AGENT — 100% Бесплатно           ║
║  Подключается к ВАШЕМУ Chrome. Никакого нового браузера. ║
╠══════════════════════════════════════════════════════════╣
║  ШАГИ ПЕРЕД ЗАПУСКОМ:                                   ║
║                                                          ║
║  1) Закройте все окна Chrome                             ║
║                                                          ║
║  2) Запустите Chrome с debug-портом (одна строка!):      ║
║  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
║                                                          ║
║  3) В открывшемся Chrome войдите в LinkedIn вручную      ║
║                                                          ║
║  4) python3 agent.py                                     ║
╚══════════════════════════════════════════════════════════╝
"""

import asyncio, json, random, sys, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# ══════════════════════════════════════════════
#  КОНФИГ — заполните под себя
# ══════════════════════════════════════════════

# --- AI (выберите один) ---
# Вариант A: Groq — БЕСПЛАТНО, регистрация на console.groq.com -> API Keys
AI_BACKEND   = "groq"
GROQ_API_KEY = "gsk_ВАШ_КЛЮЧ"           # вставьте сюда
GROQ_MODEL   = "llama-3.3-70b-versatile"

# Вариант B: Ollama — локально, офлайн, полностью бесплатно
# AI_BACKEND   = "ollama"
# OLLAMA_MODEL = "llama3"   # brew install ollama && ollama pull llama3

# --- Поиск ---
SEARCH_QUERY    = "Senior Frontend Developer"
LOCATION        = "Finland"
MAX_JOBS        = 40
ONLY_EASY_APPLY = False

# --- Данные берутся из config.json (не хранить здесь!) ---
import os as _os, json as _json

def _load_config():
    p = _os.path.join(_os.path.dirname(__file__), "config.json")
    if not _os.path.exists(p):
        print("Создайте config.json! (см. config.example.json)")
        raise SystemExit(1)
    with open(p) as f:
        return _json.load(f)

_cfg       = _load_config()
ME         = _cfg["me"]
GROQ_API_KEY = _cfg.get("groq_api_key", GROQ_API_KEY)
RESUME_PDF = _cfg.get("resume_pdf", "resume.pdf")

# ══════════════════════════════════════════════

LOG_DIR = Path("applied")
LOG_DIR.mkdir(exist_ok=True)


# ── AI calls (no external libraries) ─────────

async def ask_ai(system: str, user: str, max_tokens: int = 500) -> str:
    if AI_BACKEND == "groq":
        return await _groq(system, user, max_tokens)
    else:
        return await _ollama(user, max_tokens)


async def _groq(system: str, user: str, max_tokens: int) -> str:
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
        method="POST",
    )
    loop = asyncio.get_event_loop()
    def _call():
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    return await loop.run_in_executor(None, _call)


async def _ollama(prompt: str, max_tokens: int) -> str:
    payload = json.dumps({
        "model": "llama3",
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    loop = asyncio.get_event_loop()
    def _call():
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["response"].strip()
    return await loop.run_in_executor(None, _call)


# ── AI tasks ──────────────────────────────────

async def gen_cover_letter(title: str, company: str, desc: str) -> str:
    return await ask_ai(
        system=(
            "You write short cover letters. 3 paragraphs, under 180 words. "
            "Sound human. Open with a hook. Output ONLY the letter text."
        ),
        user=(
            f"Job: {title} at {company}\n"
            f"My background: {ME['summary']}\n"
            f"My skills: {ME['skills']}\n"
            f"Job description:\n{desc[:2000]}"
        ),
        max_tokens=350,
    )


async def answer_question(question: str, job_ctx: str, options: list = None) -> str:
    opts = f"\nChoose EXACTLY one of: {options}" if options else ""
    return await ask_ai(
        system=(
            "You fill job application forms. Give direct answers only. "
            "For work authorization questions always answer Yes. "
            "Output ONLY the answer, nothing else."
        ),
        user=(
            f"Job: {job_ctx}\nCandidate: {json.dumps(ME)}\n"
            f"Question: {question}{opts}"
        ),
        max_tokens=120,
    )


# ── Human-like input ──────────────────────────

async def wait(a=0.4, b=1.8):
    await asyncio.sleep(random.uniform(a, b))


async def human_type(el, text: str):
    await el.click()
    await wait(0.1, 0.3)
    for ch in text:
        await el.type(ch, delay=random.randint(40, 130))
    await wait(0.2, 0.4)


# ── Field mapping (no AI needed for common fields) ──

FIELD_KEYS = {
    ("first", "fname", "given"):          "first_name",
    ("last",  "lname", "family"):         "last_name",
    ("email",):                           "email",
    ("phone", "mobile", "tel"):           "phone",
    ("city",  "location"):                "location",
    ("linkedin",):                        "linkedin",
    ("year",  "experience"):              "years_experience",
    ("salary", "compensation"):           "salary_expectation",
    ("notice", "available"):              "notice_period",
    ("relocat",):                         "willing_to_relocate",
    ("sponsor",):                         "requires_sponsorship",
    ("authoriz", "eligible"):             "work_authorization",
    ("title", "position"):                "current_title",
}


def quick_answer(label: str):
    lbl = label.lower()
    for keys, me_key in FIELD_KEYS.items():
        if any(k in lbl for k in keys):
            return ME.get(me_key)
    return None


# ── Form fillers ──────────────────────────────

async def fill_input(inp, job_ctx: str):
    try:
        current = await inp.input_value()
        if current and len(current.strip()) > 1:
            return
        label = (
            await inp.get_attribute("aria-label") or
            await inp.get_attribute("placeholder") or
            await inp.get_attribute("name") or ""
        ).strip()
        val = quick_answer(label)
        if val is None:
            val = await answer_question(label or "value", job_ctx)
        await human_type(inp, str(val))
    except Exception:
        pass


async def fill_select(sel, job_ctx: str):
    try:
        label = (
            await sel.get_attribute("aria-label") or
            await sel.get_attribute("name") or "field"
        )
        options = await sel.query_selector_all("option")
        texts = [await o.inner_text() for o in options]
        texts = [t.strip() for t in texts if t.strip() and t.strip() not in ("", "Select")]
        if not texts:
            return
        best = await answer_question(label, job_ctx, options=texts)
        match = next(
            (t for t in texts if best.lower() in t.lower() or t.lower() in best.lower()),
            texts[0],
        )
        await sel.select_option(label=match)
        await wait(0.2, 0.5)
    except Exception:
        pass


async def fill_radios(fieldset, job_ctx: str):
    try:
        legend = await fieldset.query_selector("legend, .fb-dash-form-element__label")
        q = (await legend.inner_text()).strip() if legend else "question"
        labels = await fieldset.query_selector_all("label")
        texts  = [await l.inner_text() for l in labels]
        best   = await answer_question(q, job_ctx, options=texts)
        match  = next(
            (l for l, t in zip(labels, texts) if best.lower() in t.lower()),
            labels[0],
        )
        await match.click()
        await wait(0.2, 0.4)
    except Exception:
        pass


async def try_upload(container):
    upload = await container.query_selector('input[type="file"]')
    if upload:
        try:
            await upload.set_input_files(RESUME_PDF)
            print("    📎 Резюме загружено")
            await wait(1, 2)
            return True
        except Exception:
            pass
    return False


# ── LinkedIn Easy Apply ───────────────────────

async def dismiss_linkedin_popups(page):
    """Закрывает все мешающие попапы LinkedIn — resume review, tips, overlays"""
    popup_dismissals = [
        # Кнопка закрытия модалок
        'button[aria-label="Dismiss"]',
        'button[aria-label="Close"]',
        # "Skip" на экране оптимизации резюме
        'button[aria-label*="Skip"]',
        # "Not now" / "Maybe later"
        'button:has-text("Not now")',
        'button:has-text("Maybe later")',
        'button:has-text("Skip")',
        'button:has-text("Dismiss")',
        # Оверлей "improve your profile"
        '.artdeco-modal__dismiss',
        '.msg-overlay-bubble-header__controls button',
    ]
    for sel in popup_dismissals:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                print(f"    🚫 Закрываю попап: {sel}")
                await btn.click()
                await wait(0.5, 1)
        except Exception:
            pass


async def easy_apply(page, job: dict) -> bool:
    jctx = f"{job['title']} at {job['company']}"

    # Закрываем все попапы перед стартом
    await dismiss_linkedin_popups(page)
    await wait(0.5, 1)

    # Ищем кнопку Easy Apply
    btn_found = False
    for sel in [
        'button[aria-label*="Easy Apply"]',
        ".jobs-apply-button--top-card",
        "button.jobs-apply-button",
        ".jobs-s-apply button",
        'button:has-text("Easy Apply")',
    ]:
        btn = await page.query_selector(sel)
        if btn and await btn.is_visible():
            print(f"    🖱  Кликаю Easy Apply ({sel})")
            await btn.click()
            btn_found = True
            await wait(1.5, 2.5)
            break

    if not btn_found:
        # Дебаг: покажем что есть на странице
        buttons = await page.query_selector_all("button")
        btns_text = []
        for b in buttons[:10]:
            try:
                t = (await b.inner_text()).strip()
                if t:
                    btns_text.append(t)
            except Exception:
                pass
        print(f"    ⚠ Easy Apply не найден. Кнопки на странице: {btns_text}")
        return False

    # Сразу закрываем resume review экран если появился
    await wait(1, 2)
    await dismiss_linkedin_popups(page)

    # Проверяем — не попали ли на страницу LinkedIn Resume Builder
    current_url = page.url
    if "resume" in current_url.lower() or "profile" in current_url.lower():
        print(f"    ⚠ Попали на wrong page: {current_url}")
        await page.go_back()
        await wait(1.5, 2)
        return False

    cv = await gen_cover_letter(job["title"], job["company"], job.get("desc", ""))
    print("    ✍  Cover letter готов")

    for step in range(20):
        await wait(0.8, 1.5)

        # Закрываем попапы на каждом шаге
        await dismiss_linkedin_popups(page)

        modal = await page.query_selector(
            ".jobs-easy-apply-modal, .jobs-easy-apply-content, "
            "[data-test-modal-id='easy-apply-modal']"
        )
        if not modal:
            # Проверяем — может это success страница
            success_el = await page.query_selector(
                ".jobs-easy-apply-content--submitted, "
                "[data-test-modal-id='easy-apply-success-modal']"
            )
            if success_el or step > 0:
                print(f"    ✅ Отправлено! (шаг {step})")
                return True
            print(f"    ⚠ Модал не найден на шаге {step}")
            return False

        # Дебаг: что сейчас в модале
        modal_title = await modal.query_selector("h3, h2, .jobs-easy-apply-modal__title")
        if modal_title:
            title_text = (await modal_title.inner_text()).strip()
            print(f"    📋 Шаг {step+1}: {title_text}")

        await try_upload(modal)

        # Inputs
        for inp in await modal.query_selector_all(
            'input[type="text"], input[type="number"], input[type="tel"], input[type="email"]'
        ):
            await fill_input(inp, jctx)

        # Selects
        for sel in await modal.query_selector_all("select"):
            await fill_select(sel, jctx)

        # Radio groups
        for fs in await modal.query_selector_all(
            "fieldset, .jobs-easy-apply-form-section__grouping"
        ):
            if await fs.query_selector('input[type="radio"]'):
                await fill_radios(fs, jctx)

        # Textareas
        for ta in await modal.query_selector_all("textarea"):
            try:
                cur = await ta.input_value()
                if cur and len(cur.strip()) > 10:
                    continue
                lbl = (
                    await ta.get_attribute("aria-label") or
                    await ta.get_attribute("placeholder") or ""
                ).lower()
                if any(k in lbl for k in ("cover", "letter", "motivation", "why")):
                    await human_type(ta, cv)
                elif any(k in lbl for k in ("summary", "about")):
                    await human_type(ta, ME["summary"])
                else:
                    ans = await answer_question(lbl or "describe yourself", jctx)
                    await human_type(ta, ans)
            except Exception:
                pass

        # Next / Submit
        clicked = False
        for lbl in [
            "Submit application", "Review your application",
            "Continue to next step", "Next", "Submit",
        ]:
            btn = await modal.query_selector(f'button[aria-label="{lbl}"]')
            if btn and await btn.is_visible():
                txt = (await btn.inner_text()).strip()
                print(f"    → {txt}")
                await btn.click()
                await wait(1.5, 2.5)
                clicked = True
                if "submit" in txt.lower():
                    await wait(2, 3)
                    if not await page.query_selector(".jobs-easy-apply-modal"):
                        return True
                break

        if not clicked:
            primary = await modal.query_selector(".artdeco-button--primary")
            if primary and await primary.is_visible():
                await primary.click()
                await wait(1.5, 2.5)

    return False


# ── External form ─────────────────────────────

async def external_apply(ctx, job: dict) -> bool:
    page = await ctx.new_page()
    jctx = f"{job['title']} at {job['company']}"
    try:
        await page.goto(job["ext_url"], timeout=25000)
        await wait(2, 3)
        cv = await gen_cover_letter(job["title"], job["company"], job.get("desc", ""))

        for _ in range(25):
            html = await page.content()
            if any(k in html.lower() for k in [
                "application received", "thank you for applying",
                "successfully submitted", "we'll be in touch",
            ]):
                await page.close()
                return True

            await try_upload(page)

            for inp in await page.query_selector_all(
                'input[type="text"], input[type="number"], input[type="tel"], input[type="email"]'
            ):
                if await inp.is_visible():
                    await fill_input(inp, jctx)

            for ta in await page.query_selector_all("textarea"):
                if not await ta.is_visible():
                    continue
                try:
                    cur = await ta.input_value()
                    if cur and len(cur.strip()) > 10:
                        continue
                    lbl = (
                        await ta.get_attribute("aria-label") or
                        await ta.get_attribute("placeholder") or
                        await ta.get_attribute("name") or ""
                    ).lower()
                    if any(k in lbl for k in ("cover", "letter", "motivation")):
                        await human_type(ta, cv)
                    else:
                        ans = await answer_question(lbl or "field", jctx)
                        await human_type(ta, ans)
                except Exception:
                    pass

            for sel in await page.query_selector_all("select"):
                if await sel.is_visible():
                    await fill_select(sel, jctx)

            for txt in ["Submit", "Apply", "Next", "Continue"]:
                btn = await page.query_selector(f'button:has-text("{txt}")')
                if btn and await btn.is_visible():
                    print(f"    → {txt}")
                    await btn.click()
                    await wait(2, 3)
                    break

            await wait(0.5, 1)

    except Exception as e:
        print(f"    ❌ external error: {e}")
    finally:
        try:
            await page.close()
        except Exception:
            pass
    return False


# ── Scraper ───────────────────────────────────

async def scrape_jobs(page) -> list:
    url = (
        "https://www.linkedin.com/jobs/search/?"
        f"keywords={SEARCH_QUERY.replace(' ', '%20')}"
        f"&location={LOCATION.replace(' ', '%20')}"
        + ("&f_LF=f_AL" if ONLY_EASY_APPLY else "")
    )
    print(f"Ищу: {SEARCH_QUERY} / {LOCATION}")
    await page.goto(url)
    await wait(3, 5)

    jobs, seen = [], set()
    while len(jobs) < MAX_JOBS:
        await page.evaluate(
            "document.querySelector('.jobs-search-results-list')?.scrollBy(0, 2000)"
        )
        await wait(1.5, 2.5)

        for card in await page.query_selector_all(".job-card-container"):
            try:
                jid = await card.get_attribute("data-job-id") or ""
                if jid in seen:
                    continue
                seen.add(jid)

                title_el   = await card.query_selector(".job-card-list__title--link, .job-card-list__title")
                company_el = await card.query_selector(".job-card-container__company-name, .artdeco-entity-lockup__subtitle")
                link_el    = await card.query_selector("a.job-card-list__title--link, a.job-card-list__title")

                title   = (await title_el.inner_text()).strip()   if title_el   else "Unknown"
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                href    = await link_el.get_attribute("href")     if link_el    else ""
                url_job = f"https://www.linkedin.com{href}" if href.startswith("/") else href

                ea_el = await card.query_selector(".job-card-container__apply-method")
                is_ea = "easy apply" in (await ea_el.inner_text()).lower() if ea_el else False

                jobs.append({
                    "id": jid, "title": title, "company": company,
                    "url": url_job, "easy": is_ea,
                    "desc": "", "ext_url": "", "status": "pending",
                })
            except Exception:
                pass

        if len(jobs) >= MAX_JOBS:
            break
        nxt = await page.query_selector('button[aria-label="View next page"]')
        if nxt:
            await nxt.click()
            await wait(3, 5)
        else:
            break

    print(f"Найдено {len(jobs)} вакансий\n")
    return jobs[:MAX_JOBS]


async def get_desc(page, job: dict):
    try:
        await page.goto(job["url"])
        await wait(2, 3)
        desc_el = await page.query_selector(
            ".jobs-description__content, .jobs-box__html-content, .job-view-layout"
        )
        desc = (await desc_el.inner_text()).strip()[:3000] if desc_el else ""
        ext = ""
        if not job["easy"]:
            ext_el = await page.query_selector('a[href*="apply"], .jobs-apply-button--top-card a')
            ext = await ext_el.get_attribute("href") if ext_el else ""
        return desc, ext
    except Exception:
        return "", ""


def save_log(job: dict, cv: str = ""):
    path = LOG_DIR / f"{job['id']}_{job['company'].replace(' ', '_')[:25]}.json"
    path.write_text(json.dumps({**job, "cover_letter": cv, "ts": datetime.now().isoformat()},
                               ensure_ascii=False, indent=2))


# ── Main ──────────────────────────────────────

async def main():
    if not Path(RESUME_PDF).exists():
        print(f"ВНИМАНИЕ: {RESUME_PDF} не найден. Поле загрузки резюме будет пропущено.")

    async with async_playwright() as pw:
        print("Подключаюсь к вашему Chrome...")
        try:
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
        except Exception:
            print("\nНе могу подключиться к Chrome!")
            print("Запустите Chrome командой:")
            print('/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug')
            sys.exit(1)

        ctx  = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        print("Подключён! Используется ваша сессия LinkedIn.\n")

        jobs = await scrape_jobs(page)
        applied = failed = skipped = 0

        for i, job in enumerate(jobs, 1):
            ea = "Easy Apply" if job["easy"] else "External"
            print(f"[{i}/{len(jobs)}] {job['title']} @ {job['company']}  ({ea})")

            if ONLY_EASY_APPLY and not job["easy"]:
                print("    Пропущено (не Easy Apply)")
                skipped += 1
                continue

            desc, ext_url = await get_desc(page, job)
            job["desc"]    = desc
            job["ext_url"] = ext_url

            try:
                if job["easy"]:
                    await page.goto(job["url"])
                    await wait(2, 3)
                    ok = await easy_apply(page, job)
                else:
                    ok = await external_apply(ctx, job)

                job["status"] = "applied" if ok else "failed"
                if ok:
                    applied += 1
                    print("    Отклик отправлен!")
                else:
                    failed += 1
                    print("    Не удалось")
            except Exception as e:
                job["status"] = "error"
                failed += 1
                print(f"    Ошибка: {e}")

            save_log(job)
            print("    Пауза...")
            await wait(5, 10)

        print(f"\nИТОГ: отправлено {applied}, не удалось {failed}, пропущено {skipped}")
        print(f"Логи: ./{LOG_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
