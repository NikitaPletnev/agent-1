"""
╔══════════════════════════════════════════════════════════╗
║           JOB APPLICATION AGENT — OpenAI Edition        ║
║  Подключается к ВАШЕМУ Chrome. Никакого нового браузера. ║
╠══════════════════════════════════════════════════════════╣
║  ШАГИ ПЕРЕД ЗАПУСКОМ:                                   ║
║                                                          ║
║  1) Закройте все окна Chrome                             ║
║                                                          ║
║  2) Запустите Chrome с debug-портом:                     ║
║     Mac:                                                 ║
║       /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222        ║
║     Windows:                                             ║
║       chrome.exe --remote-debugging-port=9222            ║
║     Linux:                                               ║
║       google-chrome --remote-debugging-port=9222         ║
║                                                          ║
║  3) В открывшемся Chrome войдите в LinkedIn вручную      ║
║                                                          ║
║  4) python agent.py                                      ║
╚══════════════════════════════════════════════════════════╝
"""

import asyncio, json, re, random, sys
from pathlib import Path
from datetime import datetime
from openai import AsyncOpenAI
from playwright.async_api import async_playwright

# ══════════════════════════════════════════════
#  ВАШ КОНФИГ
# ══════════════════════════════════════════════

OPENAI_API_KEY = ""          # ← ваш ключ
OPENAI_MODEL   = "gpt-4o"     # gpt-4o-mini дешевле, gpt-4o точнее

# Что искать
SEARCH_QUERY     = "Frontend Developer"
LOCATION         = "EMEA"
MAX_JOBS         = 40
ONLY_EASY_APPLY  = False   # False = пробовать и внешние формы

# Ваши данные
ME = {
    "full_name":            "Ivan Petrov",
    "first_name":           "Ivan",
    "last_name":            "Petrov",
    "email":                "ivan@example.com",
    "phone":                "+1-555-0199",
    "location":             "Remote",
    "linkedin":             "linkedin.com/in/ivanpetrov",
    "years_experience":     "7",
    "current_title":        "Senior Python Developer",
    "salary_expectation":   "Negotiable",
    "notice_period":        "2 weeks",
    "willing_to_relocate":  "No",
    "work_authorization":   "Yes",
    "requires_sponsorship": "No",
    "skills": (
        "Python, FastAPI, Django, PostgreSQL, Redis, "
        "AWS, Docker, Kubernetes, REST APIs, Microservices"
    ),
    "summary": (
        "Senior Python Developer with 7 years building scalable backend systems. "
        "Expert in FastAPI, Django, PostgreSQL, AWS. Delivered high-load APIs "
        "serving millions of users, reduced latency by 45%, led teams of 5 engineers."
    ),
}

RESUME_PDF = "resume.pdf"   # путь к вашему PDF резюме

# ══════════════════════════════════════════════

ai = AsyncOpenAI(api_key=OPENAI_API_KEY)
LOG_DIR = Path("applied")
LOG_DIR.mkdir(exist_ok=True)


# ── Delays (human-like) ───────────────────────

async def wait(a=0.5, b=1.8):
    await asyncio.sleep(random.uniform(a, b))

async def type_like_human(el, text: str):
    """Набирает текст посимвольно, как человек"""
    await el.click()
    await wait(0.15, 0.4)
    for ch in text:
        await el.type(ch, delay=random.randint(35, 130))
    await wait(0.2, 0.5)


# ── OpenAI helpers ────────────────────────────

async def gpt(system: str, user: str, max_tokens=600) -> str:
    r = await ai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return r.choices[0].message.content.strip()


async def cover_letter(title: str, company: str, desc: str) -> str:
    return await gpt(
        system=(
            "You write short, punchy cover letters. "
            "3 paragraphs, under 180 words. Sound human. "
            "Open with a hook, not 'I am writing to...' "
            "Output ONLY the letter text."
        ),
        user=(
            f"Job: {title} at {company}\n"
            f"My background: {ME['summary']}\n"
            f"My skills: {ME['skills']}\n"
            f"Job description:\n{desc[:2000]}"
        ),
        max_tokens=350,
    )


async def answer(question: str, job_ctx: str, options: list = None) -> str:
    opts = f"\nChoose EXACTLY one: {options}" if options else ""
    return await gpt(
        system=(
            "You fill job application forms. "
            "Give direct answers only, no explanations. "
            "For yes/no questions about work authorization: always Yes. "
            "Output ONLY the answer."
        ),
        user=(
            f"Job: {job_ctx}\n"
            f"Candidate: {json.dumps(ME)}\n"
            f"Question: {question}{opts}"
        ),
        max_tokens=120,
    )


# ── Smart field filler ────────────────────────

FIELD_MAP = {
    # input value → key in ME dict
    ("first", "fname", "given"):                 "first_name",
    ("last",  "lname", "family", "surname"):      "last_name",
    ("email",):                                   "email",
    ("phone", "mobile", "tel"):                   "phone",
    ("city", "location", "address"):              "location",
    ("linkedin",):                                "linkedin",
    ("year",  "experience", "exp"):               "years_experience",
    ("salary", "compensation", "pay"):            "salary_expectation",
    ("notice", "start", "available"):             "notice_period",
    ("relocat",):                                 "willing_to_relocate",
    ("sponsor",):                                 "requires_sponsorship",
    ("authoriz", "eligible", "legally"):          "work_authorization",
    ("title", "position", "role"):                "current_title",
}

def map_label(label: str):
    """Матчит label поля к значению из ME"""
    lbl = label.lower()
    for keys, me_key in FIELD_MAP.items():
        if any(k in lbl for k in keys):
            return ME.get(me_key)
    return None


async def fill_input(page_or_modal, inp, job_ctx: str):
    """Заполняет один input — сначала по словарю, затем через GPT"""
    try:
        current = await inp.input_value()
        if current and len(current.strip()) > 1:
            return  # уже заполнено

        label = (
            await inp.get_attribute("aria-label") or
            await inp.get_attribute("placeholder") or
            await inp.get_attribute("name") or
            ""
        ).strip()

        val = map_label(label)
        if val is None:
            val = await answer(label or "value", job_ctx)

        await type_like_human(inp, str(val))
    except Exception:
        pass


async def fill_select(sel, job_ctx: str):
    """Выбирает опцию в <select>"""
    try:
        label = (
            await sel.get_attribute("aria-label") or
            await sel.get_attribute("name") or "field"
        )
        options = await sel.query_selector_all("option")
        texts = [await o.inner_text() for o in options]
        texts = [t for t in texts if t.strip() and t not in ("", "Select", "-- Select --")]
        if not texts:
            return
        best = await answer(label, job_ctx, options=texts)
        # ищем точное совпадение или содержащее ответ
        match = next(
            (t for t in texts if best.lower() in t.lower() or t.lower() in best.lower()),
            texts[0]
        )
        await sel.select_option(label=match)
        await wait(0.2, 0.5)
    except Exception:
        pass


async def fill_radios(fieldset, job_ctx: str):
    """Кликает нужный radio button"""
    try:
        legend = await fieldset.query_selector("legend, .fb-dash-form-element__label")
        q = await legend.inner_text() if legend else "question"
        labels = await fieldset.query_selector_all("label")
        texts  = [await l.inner_text() for l in labels]
        best   = await answer(q, job_ctx, options=texts)
        match  = next(
            (l for l, t in zip(labels, texts) if best.lower() in t.lower()),
            labels[0]
        )
        await match.click()
        await wait(0.2, 0.4)
    except Exception:
        pass


# ── Upload resume ─────────────────────────────

async def try_upload_resume(container):
    upload = await container.query_selector('input[type="file"]')
    if upload:
        try:
            await upload.set_input_files(RESUME_PDF)
            print("    📎 Резюме загружено")
            await wait(1, 2)
            return True
        except Exception as e:
            print(f"    ⚠ upload error: {e}")
    return False


# ── LinkedIn Easy Apply ───────────────────────

async def easy_apply(page, job: dict) -> bool:
    """Полный проход LinkedIn Easy Apply мультишагового модала"""
    jctx = f"{job['title']} at {job['company']}"

    # 1. Кликаем кнопку Easy Apply
    clicked = False
    for sel in [
        ".jobs-apply-button--top-card",
        "button.jobs-apply-button",
        'button[aria-label*="Easy Apply"]',
        '.jobs-s-apply button',
    ]:
        btn = await page.query_selector(sel)
        if btn and await btn.is_visible():
            await btn.click()
            clicked = True
            await wait(1.5, 2.5)
            break
    if not clicked:
        return False

    cv = await cover_letter(job["title"], job["company"], job.get("desc", ""))
    print(f"    ✍  Cover letter готов")

    # 2. Шаговый цикл
    for step in range(20):
        await wait(0.8, 1.5)

        modal = await page.query_selector(
            ".jobs-easy-apply-modal, .jobs-easy-apply-content"
        )
        if not modal:
            print(f"    ✅ Модал закрылся — отправлено! (шаг {step})")
            return True

        # Загрузка резюме
        await try_upload_resume(modal)

        # Inputs
        inputs = await modal.query_selector_all(
            'input[type="text"], input[type="number"], '
            'input[type="tel"], input[type="email"]'
        )
        for inp in inputs:
            await fill_input(modal, inp, jctx)

        # Selects
        selects = await modal.query_selector_all("select")
        for sel in selects:
            await fill_select(sel, jctx)

        # Radio groups
        fieldsets = await modal.query_selector_all(
            "fieldset, .jobs-easy-apply-form-section__grouping"
        )
        for fs in fieldsets:
            radios = await fs.query_selector_all('input[type="radio"]')
            if radios:
                await fill_radios(fs, jctx)

        # Textareas
        tas = await modal.query_selector_all("textarea")
        for ta in tas:
            try:
                cur = await ta.input_value()
                if cur and len(cur.strip()) > 10:
                    continue
                lbl = (
                    await ta.get_attribute("aria-label") or
                    await ta.get_attribute("placeholder") or ""
                ).lower()
                if any(k in lbl for k in ("cover", "letter", "motivation", "why")):
                    await type_like_human(ta, cv)
                elif "summary" in lbl or "about" in lbl:
                    await type_like_human(ta, ME["summary"])
                else:
                    ans = await answer(lbl or "describe yourself", jctx)
                    await type_like_human(ta, ans)
            except Exception:
                pass

        # Нажимаем Next / Review / Submit
        for btn_label in [
            "Submit application", "Review your application",
            "Continue to next step", "Next", "Submit",
        ]:
            btn = await modal.query_selector(
                f'button[aria-label="{btn_label}"]'
            )
            if btn and await btn.is_visible():
                txt = (await btn.inner_text()).strip()
                print(f"    → {txt}")
                await btn.click()
                await wait(1.5, 2.5)
                if "submit" in txt.lower():
                    # ждём закрытия модала
                    await wait(2, 3)
                    m = await page.query_selector(".jobs-easy-apply-modal")
                    if not m:
                        return True
                break
        else:
            # Fallback: primary button
            primary = await modal.query_selector(
                ".artdeco-button--primary"
            )
            if primary and await primary.is_visible():
                await primary.click()
                await wait(1.5, 2.5)

    return False


# ── External form (Greenhouse / Lever / custom) ──

async def external_apply(browser_ctx, job: dict) -> bool:
    """Открывает внешнюю страницу и заполняет форму"""
    page = await browser_ctx.new_page()
    jctx = f"{job['title']} at {job['company']}"

    try:
        await page.goto(job["ext_url"], timeout=25000)
        await wait(2, 3)

        cv = await cover_letter(job["title"], job["company"], job.get("desc", ""))

        for step in range(25):
            html_snippet = await page.content()

            # Проверяем успех
            if any(kw in html_snippet.lower() for kw in [
                "application received", "thank you for applying",
                "successfully submitted", "application submitted",
                "we'll be in touch",
            ]):
                await page.close()
                return True

            # Загрузка файла
            await try_upload_resume(page)

            # Inputs
            inputs = await page.query_selector_all(
                'input[type="text"], input[type="number"], '
                'input[type="tel"], input[type="email"]'
            )
            for inp in inputs:
                if await inp.is_visible():
                    await fill_input(page, inp, jctx)

            # Textareas
            tas = await page.query_selector_all("textarea")
            for ta in tas:
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
                        await type_like_human(ta, cv)
                    else:
                        ans = await answer(lbl or "describe yourself", jctx)
                        await type_like_human(ta, ans)
                except Exception:
                    pass

            # Selects
            for sel in await page.query_selector_all("select"):
                if await sel.is_visible():
                    await fill_select(sel, jctx)

            # Submit / Next button
            for txt in ["Submit", "Apply", "Next", "Continue", "Send application"]:
                btn = await page.query_selector(
                    f'button:has-text("{txt}"), input[type="submit"][value*="{txt}"]'
                )
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


# ── LinkedIn scraper ──────────────────────────

async def scrape_jobs(page) -> list[dict]:
    """Скрапит вакансии со страницы поиска LinkedIn"""
    url = (
        "https://www.linkedin.com/jobs/search/?"
        f"keywords={SEARCH_QUERY.replace(' ', '%20')}"
        f"&location={LOCATION.replace(' ', '%20')}"
        + ("&f_LF=f_AL" if ONLY_EASY_APPLY else "")
    )
    print(f"🔍 Ищу: {SEARCH_QUERY} / {LOCATION}")
    await page.goto(url)
    await wait(3, 5)

    jobs = []
    seen = set()

    while len(jobs) < MAX_JOBS:
        # Скроллим список для подгрузки карточек
        await page.evaluate(
            "document.querySelector('.jobs-search-results-list')?.scrollBy(0, 2000)"
        )
        await wait(1.5, 2.5)

        cards = await page.query_selector_all(".job-card-container")
        for card in cards:
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
                url     = f"https://www.linkedin.com{href}" if href.startswith("/") else href

                ea_el  = await card.query_selector(".job-card-container__apply-method")
                ea_txt = (await ea_el.inner_text()).lower() if ea_el else ""
                is_ea  = "easy apply" in ea_txt

                jobs.append({
                    "id":       jid,
                    "title":    title,
                    "company":  company,
                    "url":      url,
                    "easy":     is_ea,
                    "desc":     "",
                    "ext_url":  "",
                    "status":   "pending",
                })
            except Exception:
                pass

        if len(jobs) >= MAX_JOBS:
            break

        # Следующая страница
        nxt = await page.query_selector('button[aria-label="View next page"]')
        if nxt:
            await nxt.click()
            await wait(3, 5)
        else:
            break

    print(f"📋 Найдено {len(jobs)} вакансий\n")
    return jobs[:MAX_JOBS]


# ── Get job description ────────────────────────

async def get_desc(page, job: dict) -> str:
    """Открывает вакансию и достаёт описание + внешнюю ссылку"""
    try:
        await page.goto(job["url"])
        await wait(2, 3)

        # Описание
        desc_el = await page.query_selector(
            ".job-view-layout .jobs-description, "
            ".jobs-description__content, "
            ".jobs-box__html-content"
        )
        desc = (await desc_el.inner_text()).strip()[:3000] if desc_el else ""

        # Внешняя ссылка (если не Easy Apply)
        ext = ""
        if not job["easy"]:
            ext_el = await page.query_selector(
                'a[href*="apply"], .apply-button a, '
                '.jobs-apply-button--top-card a'
            )
            ext = await ext_el.get_attribute("href") if ext_el else ""

        return desc, ext
    except Exception:
        return "", ""


# ── Logger ────────────────────────────────────

def save_log(job: dict, cv: str):
    path = LOG_DIR / f"{job['id']}_{job['company'].replace(' ', '_')[:30]}.json"
    data = {**job, "cover_letter": cv, "ts": datetime.now().isoformat()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ── Main ──────────────────────────────────────

async def main():
    # Проверяем наличие resume.pdf
    if not Path(RESUME_PDF).exists():
        print(f"⚠️  Файл {RESUME_PDF} не найден! Создайте его или поменяйте RESUME_PDF в конфиге.")
        print("   (Можно взять любой PDF — агент загрузит его в поля upload)")
        sys.exit(1)

    async with async_playwright() as pw:
        print("🔗 Подключаюсь к вашему Chrome...")
        try:
            # Подключаемся к уже открытому Chrome
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
        except Exception:
            print("\n❌ Не могу подключиться к Chrome!")
            print("   Запустите Chrome с флагом: --remote-debugging-port=9222")
            print("   (Детали в шапке этого файла)")
            sys.exit(1)

        ctx  = browser.contexts[0]  # берём существующий контекст (с вашей сессией!)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print("✅ Подключён к Chrome (ваша сессия LinkedIn сохранена)\n")

        # Скрапим вакансии
        jobs = await scrape_jobs(page)

        applied, failed, skipped = 0, 0, 0

        for i, job in enumerate(jobs, 1):
            bar = f"[{i}/{len(jobs)}]"
            easy_label = "⚡ Easy Apply" if job["easy"] else "🌐 External"
            print(f"\n{bar} {job['title']} @ {job['company']}  {easy_label}")

            # Пропускаем внешние если ONLY_EASY_APPLY
            if ONLY_EASY_APPLY and not job["easy"]:
                print("    ⏭  Пропущено (не Easy Apply)")
                skipped += 1
                continue

            # Описание
            desc, ext_url = await get_desc(page, job)
            job["desc"]    = desc
            job["ext_url"] = ext_url

            cv = ""
            try:
                if job["easy"]:
                    # Переходим на страницу вакансии
                    await page.goto(job["url"])
                    await wait(2, 3)
                    ok = await easy_apply(page, job)
                else:
                    ok = await external_apply(ctx, job)

                if ok:
                    job["status"] = "applied"
                    applied += 1
                    cv = "see log"   # уже был получен внутри функций
                    print(f"    ✅ Отклик отправлен!")
                else:
                    job["status"] = "failed"
                    failed += 1
                    print(f"    ❌ Не удалось")

            except Exception as e:
                job["status"] = "error"
                job["error"]  = str(e)
                failed += 1
                print(f"    💥 Ошибка: {e}")

            save_log(job, cv)

            # Пауза между заявками (4–9 сек) — не спалиться
            print(f"    💤 Пауза...")
            await wait(4, 9)

        # Итог
        print(f"\n{'═'*50}")
        print(f"📊 СЕССИЯ ЗАВЕРШЕНА")
        print(f"   ✅ Отправлено:  {applied}")
        print(f"   ❌ Не удалось:  {failed}")
        print(f"   ⏭  Пропущено:  {skipped}")
        print(f"   📁 Логи: ./{LOG_DIR}/")
        print(f"{'═'*50}")


if __name__ == "__main__":
    asyncio.run(main())
