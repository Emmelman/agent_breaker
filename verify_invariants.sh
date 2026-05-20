#!/bin/bash
# Проверка инвариантов Agent-Breaker v2
# Запускать после КАЖДОГО изменения: bash v2/verify_invariants.sh

echo "=== Проверка инвариантов ==="
FAIL=0

check() {
    local name="$1" expected="$2" actual="$3"
    if [ "$expected" = ">0" ] && [ "$actual" -gt 0 ]; then
        echo "  PASS $name: $actual"
    elif [ "$expected" = "0" ] && [ "$actual" -eq 0 ]; then
        echo "  PASS $name: $actual"
    elif [ "$expected" = "$actual" ]; then
        echo "  PASS $name: $actual"
    else
        echo "  FAIL $name: expected $expected, got $actual"
        FAIL=1
    fi
}

# UI инварианты
echo ""
echo "--- UI ---"
check "UI-1 (📤 preview)" ">0" "$(grep -c '📤' v2/ui/app.py)"
check "UI-2a (Детали)" ">0" "$(grep -c '"Детали"' v2/ui/app.py)"
check "UI-2b (НЕТ Полный текст)" "0" "$(grep -c 'Полный текст' v2/ui/app.py)"
check "UI-3 (НЕТ .move)" "0" "$(grep -c '\.move(' v2/ui/app.py)"
check "UI-5 (_update_activity)" ">0" "$(grep -c '_update_activity' v2/ui/app.py)"

# LLM инварианты
echo ""
echo "--- LLM ---"
check "LLM-1 (strip_llm_wrapper)" ">0" "$(grep -rl 'strip_llm_wrapper' v2/core/*.py 2>/dev/null | wc -l)"
check "LLM-2 (LLMFactory())" ">0" "$(grep -c 'LLMFactory()' v2/ui/app.py)"

# Pipeline инварианты
echo ""
echo "--- Pipeline ---"
check "PIPE-1 (empty guard)" ">0" "$(grep -c 'startswith.*ERROR' v2/core/response_scorer.py)"
check "PIPE-2 (try/except)" ">0" "$(grep -c 'except Exception' v2/ui/app.py)"
check "PIPE-3 (should_stop)" ">0" "$(grep -c 'should_stop' v2/ui/app.py)"

# Data инварианты
echo ""
echo "--- Data ---"
check "DATA-1 (all_attack_results)" ">0" "$(grep -c 'all_attack_results' v2/models/schemas.py)"
check "DATA-2 (activity_log)" ">0" "$(grep -c 'activity_log' v2/models/schemas.py)"

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "=== ВСЕ ИНВАРИАНТЫ ПРОЙДЕНЫ ==="
else
    echo "=== ЕСТЬ НАРУШЕНИЯ — ИСПРАВИТЬ ДО КОММИТА ==="
    exit 1
fi
