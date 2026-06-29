import re
import random
import time
import os
from typing import List, Optional

# Importuri pentru clienți
try:
    from google import genai
except Exception:
    genai = None

try:
    from huggingface_hub import InferenceClient
except Exception:
    InferenceClient = None

try:
    from groq import Groq
except Exception:
    Groq = None

# --- Funcțiile de utilitate ---
SUPERSCRIPTS = str.maketrans("0123456789-+()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺⁽⁾ⁿ")
def _to_superscript(expr: str) -> str:
    return expr.translate(SUPERSCRIPTS)

def normalize_math_text(s: str) -> str:
    if not s: 
        return s
    return s.strip()

def _extract_lines(text: str) -> List[str]:
    text = (text or "").replace("\r", "\n")
    raw = [l.strip() for l in text.split("\n") if l.strip()]
    out = []
    for l in raw:
        l = re.sub(r"^(?:\d+[\.\)\-:]?\s*|[\-\*•]\s*)", "", l)
        if len(l) >= 10:
            out.append(normalize_math_text(l))
    seen = set()
    return [x for x in out if not (x.lower() in seen or seen.add(x.lower()))]

def _prompt(subject: str, level: str, difficulty: str, n: int, topic: str = "") -> str:
    base = f"""
Generează EXACT {n} probleme originale de {subject} pentru clasa / nivelul {level}, dificultate {difficulty}.

Reguli OBLIGATORII:
1. Problemele trebuie să fie diferite între ele.
2. Fiecare problemă trebuie să fie clar formulată, potrivită pentru elevi.
3. Nu repeta aceeași structură sau aceleași valori numerice.
4. Nu include soluții, explicații, titluri sau numerotare.
5. Scrie doar enunțurile finale.
6. Problemele trebuie să fie potrivite pentru nivelul indicat, fără concepte din clase mai mari.
"""

    if topic:
        base += f"""
IMPORTANT:
Toate problemele trebuie să fie strict despre subiectul / conceptul:
{topic}
"""

    base += """
Scrie toate formulele matematice în format LaTeX între simboluri $...$.

Exemple corecte:
$x^2 - 5x + 6 = 0$
$\\frac{3}{4}$
$\\sqrt{49}$

Afișează fiecare problemă pe linie separată.
"""

    return base.strip()

# --- CLIENȚII AI ---

def gen_gemini(api_key: str, model: str, subject: str, level: str, difficulty: str, n: int, topic: str = "") -> List[str]:
    if not (genai and api_key): return []
    client = genai.Client(api_key=api_key)
    
    for attempt in range(2):
        try:
            r = client.models.generate_content(model=model, contents=_prompt(subject, level, difficulty, n, topic))
            return _extract_lines(getattr(r, "text", ""))
        except Exception as e:
            print(f"GEMINI ERROR (Încercarea {attempt+1}):", repr(e))
            if attempt == 0:
                time.sleep(1)
    return []

def gen_groq(api_key: str, model: str, subject: str, level: str, difficulty: str, n: int, topic: str = "") -> List[str]:
    if not (Groq and api_key): return []
    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _prompt(subject, level, difficulty, n, topic)}],
        )
        return _extract_lines(completion.choices[0].message.content)
    except Exception as e:
        print("GROQ ERROR:", repr(e))
        return []

def gen_hf(token: str, model: str, subject: str, level: str, difficulty: str, n: int, topic: str = "") -> List[str]:
    if not (InferenceClient and token): return []
    try:
        client = InferenceClient(model=model, token=token)
        r = client.chat_completion(
            messages=[{"role": "user", "content": _prompt(subject, level, difficulty, n, topic)}],
            max_tokens=800
        )
        return _extract_lines(r.choices[0].message.content)
    except Exception as e:
        print("HF ERROR:", repr(e))
        return []
def dedupe_generated_items(items):
    seen = set()
    out = []

    for source, text in items:
        key = normalize_math_text(text).lower()
        if key not in seen:
            seen.add(key)
            out.append((source, text))

    return out
def gen_local(subject, level, difficulty, n, topic=""):
    # Simulare locală simplă, includem topicul dacă există
    topic_str = f" despre {topic}" if topic else ""
    return [f"Problemă de rezervă {i+1} ({subject}{topic_str}): Calculează rezultatul pentru nivelul {level}." for i in range(n)]

# --- LOGICA DE FALLBACK ---

def generate_multi(gemini_key, gemini_model, hf_token, hf_model, subject, level, difficulty, n, topic=""):
    items = []

    # 1. Încercăm GROQ (Primar - ultra rapid)
    groq_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if groq_key:
        for t in gen_groq(groq_key, groq_model, subject, level, difficulty, n, topic):
            items.append(("groq", t))
        if len(items) >= n: return items[:n]

    # 2. Încercăm GEMINI (Rezervă principală)
    if len(items) < n:
        missing = n - len(items)
        for t in gen_gemini(gemini_key, gemini_model, subject, level, difficulty, missing, topic):
            items.append(("gemini", t))
        if len(items) >= n: return items[:n]

    # 3. Încercăm HUGGING FACE (Rezervă Finală AI)
    if len(items) < n:
        missing = n - len(items)
        for t in gen_hf(hf_token, hf_model, subject, level, difficulty, missing, topic):
            items.append(("hf", t))
        if len(items) >= n: return items[:n]

    # 4. LOCAL (Dacă totul e picat)
    if len(items) < n:
        missing = n - len(items)
        for t in gen_local(subject, level, difficulty, missing, topic):
            items.append(("local", t))
    items = dedupe_generated_items(items)
    return items[:n]
def build_similar_prompt(subject: str, level: str, difficulty: str, n: int, examples: list[str]) -> str:
    block = "\n\n".join(
        [f"Exemplul {i+1}:\n{ex}" for i, ex in enumerate(examples)]
    )

    return f"""
Generează EXACT {n} probleme NOI de {subject} pentru nivelul {level}, dificultate {difficulty}.

Problemele trebuie să fie asemănătoare cu exemplele de mai jos ca stil, structură și tip de exercițiu, dar NU au voie să fie copii.
Schimbă formularea și valorile numerice unde este cazul.
Nu include soluții, explicații, titluri sau numerotare.
Scrie formulele în LaTeX între $...$.
Afișează fiecare problemă pe linie separată.

Exemple:
{block}
""".strip()

def gen_gemini_from_prompt(api_key: str, model: str, prompt: str) -> List[str]:
    if not (genai and api_key):
        return []
    client = genai.Client(api_key=api_key)
    for attempt in range(2):
        try:
            r = client.models.generate_content(model=model, contents=prompt)
            return _extract_lines(getattr(r, "text", ""))
        except Exception:
            if attempt == 0:
                time.sleep(1)
    return []


def gen_groq_from_prompt(api_key: str, model: str, prompt: str) -> List[str]:
    if not (Groq and api_key):
        return []
    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_lines(completion.choices[0].message.content)
    except Exception:
        return []


def gen_hf_from_prompt(token: str, model: str, prompt: str) -> List[str]:
    if not (InferenceClient and token):
        return []
    try:
        client = InferenceClient(model=model, token=token)
        r = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800
        )
        return _extract_lines(r.choices[0].message.content)
    except Exception:
        return []
    
def generate_similar_multi(gemini_key, gemini_model, hf_token, hf_model, subject, level, difficulty, n, examples):
    prompt = build_similar_prompt(subject, level, difficulty, n, examples)
    items = []

    groq_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    if groq_key:
        for t in gen_groq_from_prompt(groq_key, groq_model, prompt):
            items.append(("groq", t))
        if len(items) >= n:
            return dedupe_generated_items(items)[:n]

    if len(items) < n:
        missing = n - len(items)
        for t in gen_gemini_from_prompt(gemini_key, gemini_model, prompt):
            items.append(("gemini", t))
        if len(items) >= n:
            return dedupe_generated_items(items)[:n]

    if len(items) < n:
        for t in gen_hf_from_prompt(hf_token, hf_model, prompt):
            items.append(("hf", t))

    items = dedupe_generated_items(items)
    return items[:n]
