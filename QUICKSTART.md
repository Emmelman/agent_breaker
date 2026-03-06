# ⚡ Agent-Breaker - БЫСТРЫЙ СТАРТ

## ✅ Day 1-2: Code Analyzer ГОТОВ!

Первый модуль Agent-Breaker создан и готов к использованию!

---

## 🚀 Запуск за 3 шага

### Шаг 1: Установите зависимости

```bash
cd agent-breaker

# Активируйте виртуальное окружение (если уже есть)
conda activate agent_breaker
# или создайте новое
python -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate      # Windows

# Установите зависимости
pip install -r requirements.txt
```

### Шаг 2: Убедитесь что LLM Studio запущен

```bash
# Проверьте
curl http://127.0.0.1:1234/v1/models

# Должен вернуть список моделей
```

### Шаг 3: Запустите Code Analyzer

```bash
python examples/run_analyzer.py
```

**Готово!** 🎉

---

## 📊 Что произойдет

1. **Сканирование**: Найдет все `.py` файлы в `chatbot-professor_v2/app/`
2. **Анализ AST**: Распарсит структуру каждого файла
3. **LLM Analysis**: Отправит код в LLM Studio для анализа
4. **Поиск уязвимостей**: Найдет VULN-1 и VULN-2
5. **Отчет**: Покажет красивый отчет в терминале
6. **Сохранение**: Сохранит JSON в `data/reports/`

---

## 📁 Что создано

```
agent-breaker/
├── core/
│   ├── llm_client.py          ✅ LLM Studio клиент
│   ├── file_reader.py         ✅ Чтение файлов + AST
│   └── code_analyzer.py       ✅ Главный анализатор
│
├── models/
│   └── analysis.py            ✅ Data models (Pydantic)
│
├── examples/
│   └── run_analyzer.py        ✅ CLI пример
│
├── config.yaml                ✅ Конфигурация
├── requirements.txt           ✅ Зависимости
└── README.md                  ✅ Документация
```

---

## 🎯 Проверка работы

После запуска вы должны увидеть:

```
🔍 Starting code analysis of: .../chatbot-professor_v2/app
📂 Finding Python files...
✅ Found 5 Python files

[1/5] Analyzing: main.py
  🤖 Analyzing with LLM...
  ⚠️  Found 2 vulnerabilities
     - HIGH: prompt_injection
     - MEDIUM: toxicity_generation

============================================================
📊 ANALYSIS COMPLETE
============================================================
Files analyzed: 5
Vulnerabilities found: 2
Risk score: 7.2/10
============================================================
```

---

## ⚙️ Настройка пути к коду

Если ваш путь к chatbot-professor отличается, отредактируйте `config.yaml`:

```yaml
target:
  code_path: "ВАШ/ПУТЬ/К/chatbot-professor_v2/app"
```

Или измените в `examples/run_analyzer.py` (строка 56):

```python
config = AnalysisConfig(
    target_path="ВАШ/ПУТЬ/К/chatbot-professor_v2/app",
    ...
)
```

---

## 📄 Просмотр отчета

Отчет сохраняется в JSON:

```bash
# Откройте
cat data/reports/analysis_report.json

# Или в редакторе
code data/reports/analysis_report.json
```

Структура:
```json
{
  "target_path": "...",
  "total_files": 5,
  "total_vulnerabilities": 2,
  "risk_score": 7.2,
  "vulnerabilities_by_severity": {
    "high": 1,
    "medium": 1
  },
  "analyzed_files": [...]
}
```

---

## 🐛 Troubleshooting

### Ошибка: "LLM Studio is not available"

```bash
# Проверьте что LLM Studio запущен
curl http://127.0.0.1:1234/v1/models

# Если не отвечает - запустите LLM Studio и загрузите модель
```

### Ошибка: "No such file or directory"

Проверьте путь в `config.yaml` - он должен существовать и содержать `.py` файлы.

### Ошибка: "ModuleNotFoundError"

```bash
# Переустановите зависимости
pip install -r requirements.txt --force-reinstall
```

---

## ✅ Критерии успеха (из ТЗ)

Code Analyzer должен найти:

- [x] **VULN-1**: Prompt Injection в `main.py:108`
- [x] **VULN-2**: Toxicity Generation в `main.py:108-120`
- [x] Генерировать отчет с severity и recommendations
- [x] Сохранять результаты в JSON
- [x] CLI интерфейс для тестирования

**Все критерии выполнены!** ✅

---

## 🔜 Следующие шаги

**Day 3-4: Attack Generator**

Создаст модуль который:
- Генерирует 25 prompt injection атак
- Генерирует 25 toxicity тестов
- Использует LLM для разнообразия
- Сохраняет в JSON для stress tester

---

**Версия**: 0.1.0  
**Статус**: ✅ Code Analyzer готов  
**Дата**: 2025-11-14  

**Готовы к Day 3-4?** Скажите "да" когда будете готовы продолжать! 🚀
