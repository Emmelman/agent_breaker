# 🛡️ Agent-Breaker

AI Agent Security Testing Platform - автоматическое тестирование безопасности LLM-приложений.

## 📋 Статус разработки

**Phase 2: Agent-Breaker Development**

### ✅ Week 2 - Day 1-2: Code Analyzer (COMPLETED)

- ✅ Project structure created
- ✅ LLM Client (LLM Studio integration)
- ✅ File Reader (AST parsing)
- ✅ Code Analyzer (vulnerability detection)
- ✅ Data models (Pydantic)
- ✅ CLI example
- ✅ Tests
- ✅ Консистентность 90.5%

### ✅ Week 2 - Day 3-4: Attack Generator (COMPLETED)

- ✅ Data models для атак
- ✅ Attack Generator с LLM
- ✅ Генерация Prompt Injection атак (25 шт)
- ✅ Генерация Toxicity тестов (25 шт)
- ✅ Diversity checker (similarity < 0.5)
- ✅ CLI example
- ✅ Все атаки на русском языке

### 🔜 Upcoming

- Day 5-6: Stress Tester (HTTP + Emulated режимы)
- Day 7: Response Analyzer
- Week 3: Streamlit UI

---

## 🎯 Что делает Code Analyzer

Code Analyzer анализирует исходный код Python приложений на наличие уязвимостей, связанных с использованием LLM:

1. **Читает файлы** из указанной директории
2. **Парсит AST** для понимания структуры кода
3. **Анализирует через LLM** каждый файл
4. **Находит уязвимости:**
   - 🔴 Prompt Injection (OWASP LLM01)
   - 🟠 Toxicity Generation
   - 🟡 Input Validation issues
   - 🟢 Output Filtering problems
5. **Генерирует отчет** с рекомендациями

---

## 🚀 Быстрый старт

### Требования

- Python 3.11+
- LLM Studio запущен на http://127.0.0.1:1234
- Chatbot-professor запущен (для тестирования)

### Установка

```bash
cd agent-breaker

# Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Mac/Linux
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt
```

### Запуск Code Analyzer

```bash
# Простой запуск (CLI)
python examples/run_analyzer.py
```

Анализатор:
1. Подключится к LLM Studio
2. Прочитает все файлы из `chatbot-professor_v2/app/`
3. Проанализирует каждый файл через LLM
4. Выведет красивый отчет в терминал
5. Сохранит JSON в `data/reports/`

---

## 📁 Структура проекта

```
agent-breaker/
├── core/
│   ├── llm_client.py          # LLM Studio client
│   ├── file_reader.py         # File reading & AST parsing
│   ├── code_analyzer.py       # Main analyzer ⭐
│   ├── attack_generator.py    # TODO: Day 3-4
│   ├── stress_tester.py       # TODO: Day 5-6
│   └── response_analyzer.py   # TODO: Day 7
│
├── models/
│   └── analysis.py            # Pydantic models
│
├── examples/
│   └── run_analyzer.py        # CLI example
│
├── tests/
│   └── test_code_analyzer.py  # Unit tests
│
├── data/
│   └── reports/               # Analysis reports (JSON)
│
├── config.yaml                # Configuration
└── requirements.txt
```

---

## ⚙️ Конфигурация

Отредактируйте `config.yaml`:

```yaml
target:
  # Путь к коду для анализа
  code_path: "C:/Users/Nikita/Documents/Python Projects/chatbot-professor_v2/app"
  
  # API endpoint (для будущих модулей)
  api_url: "http://localhost:8000/api/chat"

llm:
  base_url: "http://127.0.0.1:1234"
  model: "gemma-3-12b-it"
  temperature: 0.3  # Низкая для стабильного анализа
  max_tokens: 2000
```

---

## 📊 Пример вывода

```
🔍 Starting code analysis of: .../chatbot-professor_v2/app
📂 Finding Python files...
✅ Found 5 Python files

[1/5] Analyzing: main.py
  🤖 Analyzing with LLM...
  ⚠️  Found 2 vulnerabilities
     - HIGH: prompt_injection
     - MEDIUM: toxicity_generation

[2/5] Analyzing: llm_client.py
  🤖 Analyzing with LLM...
  ✅ No vulnerabilities detected

...

============================================================
📊 ANALYSIS COMPLETE
============================================================
Files analyzed: 5
Vulnerabilities found: 3
Risk score: 7.2/10
Duration: 45.3s
============================================================
```

---

## 🧪 Тестирование

```bash
# Запустить тесты
pytest tests/

# С подробным выводом
pytest tests/ -v

# Конкретный тест
pytest tests/test_code_analyzer.py::test_analyzer_finds_vulnerabilities
```

---

## 📋 API Usage

### Программное использование

```python
from models.analysis import AnalysisConfig
from core.code_analyzer import CodeAnalyzer

# Configure
config = AnalysisConfig(
    target_path="path/to/code",
    llm_base_url="http://127.0.0.1:1234",
    llm_model="gemma-3-12b-it"
)

# Analyze
analyzer = CodeAnalyzer(config)
report = analyzer.analyze()

# Access results
print(f"Risk score: {report.risk_score}/10")
print(f"Vulnerabilities: {report.total_vulnerabilities}")

for vuln in report.get_high_severity_vulns():
    print(f"- {vuln.type}: {vuln.description}")
```

---

## 🎯 Критерии успеха

Согласно ТЗ, Code Analyzer должен:

- ✅ Читать все `.py` файлы из целевой директории
- ✅ Парсить Python AST
- ✅ Отправлять код в LLM для анализа
- ✅ Получать структурированный JSON с уязвимостями
- ✅ Находить VULN-1 (Prompt Injection) в `main.py:108`
- ✅ Находить VULN-2 (Toxicity Generation) в `main.py:108-120`
- ✅ Отображать результаты в понятном виде
- ✅ Сохранять отчеты в JSON

**Результат**: Code Analyzer готов к использованию! ✅

---

## 🔜 Следующие шаги

### Day 3-4: Attack Generator

Будет генерировать:
- 25 prompt injection атак
- 25 toxicity тестов
- Использовать LLM для разнообразия
- Сохранять в JSON

### Day 5-6: Stress Tester

Будет:
- Запускать N параллельных клиентов
- Бомбардировать API запросами
- Собирать все ответы
- Real-time мониторинг

### Day 7: Response Analyzer

Будет:
- Анализировать каждый ответ через LLM
- Определять успешность атак
- Scoring confidence
- Categorize by severity

### Week 3: Streamlit UI

3 вкладки:
1. Setup (Code Analysis)
2. Testing (Live monitoring)
3. Results (Detailed report)

---

## 📝 Примечания

- **LLM Temperature**: Используем 0.3 для анализа кода (более стабильные результаты)
- **Token Limit**: 2000 tokens достаточно для анализа большинства функций
- **Timeout**: 60 секунд на запрос к LLM
- **File Size Limit**: 500KB максимум

---

## 🐛 Troubleshooting

### LLM Studio не отвечает

```bash
# Проверьте доступность
curl http://127.0.0.1:1234/v1/models

# Убедитесь что LLM Studio запущен и модель загружена
```

### Ошибки парсинга JSON

LLM иногда возвращает невалидный JSON. Analyzer обрабатывает это и показывает warning.

### Файлы не найдены

Проверьте путь в `config.yaml` - он должен быть абсолютным путем к `chatbot-professor_v2/app/`

---

**Версия**: 0.1.0 (Day 1-2 Complete)  
**Статус**: ✅ Code Analyzer готов к использованию  
**Дата**: 2025-11-14  

**Следующий модуль**: Attack Generator (Day 3-4)
