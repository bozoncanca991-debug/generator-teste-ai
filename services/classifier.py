import re

def classify_problem(subject: str, text: str):
    """
    Întoarce: (pred_level, pred_difficulty, confidence)
    Clasificare simplă bazată pe reguli (AI light).
    """

    t = text.lower()

    # --- nivel ---
    if any(k in t for k in ["integral", "derivat", "limită", "funcție", "trigonometr"]):
        level = "XI-XII"
    elif any(k in t for k in ["ecuație de gradul ii", "sistem", "parabol", "funcție"]):
        level = "VIII-IX"
    elif any(k in t for k in ["adun", "scad", "înmul", "fracț", "procent"]):
        level = "V-VI"
    else:
        level = "VII-VIII"

    # --- dificultate ---
    score = 0
    if len(text) > 120:
        score += 1
    if any(k in t for k in ["demonstrează", "arată că", "justifică"]):
        score += 2
    if any(k in t for k in ["optim", "maxim", "minim"]):
        score += 1
    if text.count(",") + text.count(";") >= 3:
        score += 1

    if score <= 1:
        diff = "ușor"
    elif score <= 3:
        diff = "mediu"
    else:
        diff = "greu"

    confidence = min(0.9, 0.5 + score * 0.1)

    return level, diff, round(confidence, 2)
