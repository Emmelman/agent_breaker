"""
Конвертация CSV-файлов в единый JSON knowledge base.

Входные файлы:
  - Факторы и меры.csv   (risk factors / UFR)
  - Факторы и меры2.csv  (mitigations / UMF)
  - Факторы и меры3.csv  (risk → factor → mitigation mapping)

Выходной файл: knowledge/knowledge_base.json
"""

import csv
import json
import re
import sys
from pathlib import Path

# Корень проекта — на уровень выше v2/
PROJECT_ROOT = Path(__file__).parent.parent

# Входные CSV
FACTORS_CSV = PROJECT_ROOT / "Факторы и меры.csv"
MITIGATIONS_CSV = PROJECT_ROOT / "Факторы и меры2.csv"
MAPPINGS_CSV = PROJECT_ROOT / "Факторы и меры3.csv"

# Выходной JSON
OUTPUT_DIR = Path(__file__).parent / "knowledge"
OUTPUT_FILE = OUTPUT_DIR / "knowledge_base.json"

# Наш scope: 5 рисков для тестирования
OUR_SCOPE = ["TOXIC", "HALL", "DISINFO", "AGENCY", "GH_RCE"]

RISK_LABELS = {
    "DPI": "directInjections",
    "TOXIC": "toxicity",
    "AGENCY": "excessiveAutonomy",
    "SUPPLY": "configurationVulnerability",
    "KNOW": "degradation",
    "LEAK": "dataLeak",
    "IPI": "indirectInjections",
    "HALL": "hallucination",
    "DISINFO": "disinformation",
    "MULTI": "multiagentInteractionFailure",
    "GH_RCE": "hiddenGoals",
    "LIMIT": "resourceAbuse",
    "TOOLS": "incorrectToolUsage",
}

RISK_FULL_NAMES = {
    "DPI": "Прямые prompt-инъекции",
    "TOXIC": "Генерация токсичного контента",
    "AGENCY": "Чрезмерная автономность",
    "SUPPLY": "Уязвимости конфигурации",
    "KNOW": "Деградация знаний",
    "LEAK": "Утечка данных",
    "IPI": "Непрямые prompt-инъекции",
    "HALL": "Галлюцинации",
    "DISINFO": "Дезинформация",
    "MULTI": "Сбои межагентного взаимодействия",
    "GH_RCE": "Скрытые цели / удалённое выполнение",
    "LIMIT": "Злоупотребление ресурсами",
    "TOOLS": "Некорректное использование инструментов",
}


def _is_ufr_id(value: str) -> bool:
    """Проверяет, является ли строка корректным UFR ID."""
    return bool(re.match(r"^UFR-\d+$", value.strip()))


def _is_umf_id(value: str) -> bool:
    """Проверяет, является ли строка корректным UMF ID."""
    return bool(re.match(r"^UMF-\d+$", value.strip()))


def _clean(value: str) -> str:
    """Очистка строки от лишних пробелов."""
    return value.strip()


def parse_factors(filepath: Path) -> dict:
    """Парсит CSV с risk factors (UFR)."""
    factors = {}
    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Строка заголовков — 4-я (индекс 3): №, ГРУППА, UFR ID, ...
    header_idx = None
    for i, row in enumerate(rows):
        if len(row) >= 5 and row[2].strip() == "UFR ID":
            header_idx = i
            break

    if header_idx is None:
        print("ОШИБКА: не найден заголовок в Факторы и меры.csv")
        sys.exit(1)

    for row in rows[header_idx + 1 :]:
        if len(row) < 6:
            continue
        ufr_id = _clean(row[2])
        if not _is_ufr_id(ufr_id):
            continue

        short_name = _clean(row[4])
        description = _clean(row[5])
        group = _clean(row[6]) if len(row) > 6 else ""
        activated_by = _clean(row[7]) if len(row) > 7 else ""
        evidence = _clean(row[8]) if len(row) > 8 else ""
        llm_prompt = _clean(row[9]) if len(row) > 9 else ""

        # Пропускаем авто-вычисляемые поля
        if evidence.startswith("→ Вычисляется"):
            evidence = ""
        if llm_prompt.startswith("→ Вычисляется"):
            llm_prompt = ""

        activated_by_val = activated_by if _is_umf_id(activated_by) else None

        factors[ufr_id] = {
            "id": ufr_id,
            "short_name": short_name,
            "group": group,
            "description": description,
            "evidence_guide": evidence,
            "llm_audit_prompt": llm_prompt,
            "activated_by_missing": activated_by_val,
            "risks": [],
        }

    return factors


def parse_mitigations(filepath: Path) -> dict:
    """Парсит CSV с mitigations (UMF)."""
    mitigations = {}
    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Ищем заголовок: Группа, TTT, ГРУППА, UMF ID, Short Name, ...
    header_idx = None
    for i, row in enumerate(rows):
        if len(row) >= 4 and row[3].strip() == "UMF ID":
            header_idx = i
            break

    if header_idx is None:
        print("ОШИБКА: не найден заголовок в Факторы и меры2.csv")
        sys.exit(1)

    for row in rows[header_idx + 1 :]:
        if len(row) < 6:
            continue

        umf_id = _clean(row[1])
        if not _is_umf_id(umf_id):
            continue

        # CSV2: col0=Группа, col1=UMF ID, col2=ГРУППА, col3=Short Name,
        #        col4=Описание, col5=Группа(коды), col6=Активирует UFR,
        #        col7=Evidence, col8=Audit Prompt
        short_name = _clean(row[3])
        description = _clean(row[4])

        group = _clean(row[0])
        activates_ufr = _clean(row[6]) if len(row) > 6 else ""
        evidence = _clean(row[7]) if len(row) > 7 else ""

        # Пропускаем записи без short_name (дефект данных)
        if not short_name:
            continue

        # Фоллбэк: если описание пусто, берём из evidence
        if not description and evidence:
            description = evidence

        activates_val = activates_ufr if _is_ufr_id(activates_ufr) else None

        mitigations[umf_id] = {
            "id": umf_id,
            "short_name": short_name,
            "group": group,
            "description": description,
            "evidence_guide": evidence,
            "activates_ufr": activates_val,
        }

    return mitigations


def parse_mappings(filepath: Path) -> list:
    """Парсит CSV с маппингами risk → factor → mitigation."""
    mappings = []
    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Пропускаем заголовки (первые 2 строки)
    for row in rows[2:]:
        if len(row) < 3:
            continue

        risk = _clean(row[0])
        factor = _clean(row[1])
        mitigation = _clean(row[2])
        dual = _clean(row[3]) if len(row) > 3 else ""

        if not risk or not _is_ufr_id(factor):
            continue

        mapping = {
            "risk": risk,
            "factor": factor,
            "mitigation": mitigation if _is_umf_id(mitigation) else "",
            "dual": dual.strip() if dual.strip() and _is_umf_id(dual.strip()) else None,
        }
        mappings.append(mapping)

    return mappings


def build_risks(mappings: list) -> dict:
    """Построение словаря рисков из маппингов (только наш scope)."""
    risks = {}
    for risk_id in OUR_SCOPE:
        factors_set = set()
        for m in mappings:
            if m["risk"] == risk_id:
                factors_set.add(m["factor"])

        risks[risk_id] = {
            "id": risk_id,
            "name": RISK_LABELS.get(risk_id, risk_id),
            "full_name": RISK_FULL_NAMES.get(risk_id, risk_id),
            "factors": sorted(factors_set),
        }

    return risks


def enrich_factors_with_risks(factors: dict, mappings: list) -> None:
    """Добавляет список рисков в каждый фактор на основе маппингов."""
    for m in mappings:
        ufr_id = m["factor"]
        risk_id = m["risk"]
        if ufr_id in factors and risk_id not in factors[ufr_id]["risks"]:
            factors[ufr_id]["risks"].append(risk_id)

    # Сортируем для детерминированности
    for factor in factors.values():
        factor["risks"].sort()


def main() -> None:
    """Основная функция конвертации."""
    print("Парсинг CSV-файлов...")

    factors = parse_factors(FACTORS_CSV)
    print(f"  Факторов (UFR): {len(factors)}")

    mitigations = parse_mitigations(MITIGATIONS_CSV)
    print(f"  Мер (UMF): {len(mitigations)}")

    mappings = parse_mappings(MAPPINGS_CSV)
    print(f"  Маппингов: {len(mappings)}")

    risks = build_risks(mappings)
    print(f"  Рисков в scope: {len(risks)}")

    enrich_factors_with_risks(factors, mappings)

    # Собираем итоговый JSON
    kb = {
        "risks": risks,
        "factors": dict(sorted(factors.items())),
        "mitigations": dict(sorted(mitigations.items())),
        "mappings": mappings,
        "our_scope": OUR_SCOPE,
        "risk_labels": RISK_LABELS,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)

    print(f"\nГотово! Записано в {OUTPUT_FILE}")

    # Проверочная статистика
    for risk_id in OUR_SCOPE:
        n_factors = len(risks[risk_id]["factors"])
        print(f"  {risk_id}: {n_factors} факторов")


if __name__ == "__main__":
    main()
