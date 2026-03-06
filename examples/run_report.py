"""
Report Generator - детальный отчёт о безопасности агента.

Читает размеченный JSON (с _labeled суффиксом) и генерирует:
- Структурированный отчёт в консоль (Rich)
- Текстовый файл рядом с JSON

ВАЖНО: Выводит КАЖДУЮ реализовавшуюся атаку ПОЛНОСТЬЮ без сокращений.

Usage:
    python examples/run_report.py data/test_runs/hybrid_test_abc123_labeled.json
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.constants import ResistanceLevel, ExploitationLevel


# Словари для человекочитаемых названий
ATTACK_TYPE_RU = {
    "prompt_injection": "Внедрение инструкций (Prompt Injection)",
    "toxicity_test": "Токсичность / Вредоносный контент",
}

TECHNIQUE_RU = {
    "instruction_bypass": "Прямой обход инструкций",
    "role_manipulation": "Манипуляция ролью агента",
    "context_override": "Переопределение контекста",
    "encoding_trick": "Закодированная инструкция",
    "jailbreak": "Джейлбрейк",
    "indirect_injection": "Косвенное внедрение",
    "system_prompt_extraction": "Извлечение системного промпта",
    "context_overflow": "Переполнение контекста",
    "discriminatory": "Дискриминационный запрос",
    "aggressive": "Агрессия / Оскорбление",
    "hate_speech": "Язык ненависти",
    "explicit": "Явно вредоносный контент",
}

PHASE_RU = {
    "rapport": "Установление доверия",
    "context_poisoning": "Отравление контекста",
    "gradual_escalation": "Постепенная эскалация",
    "payload_delivery": "Доставка полезной нагрузки",
}


class ReportGenerator:
    """Генератор детального отчёта о безопасности"""
    
    def __init__(self, json_path: str):
        self.json_path = Path(json_path)
        self.console = Console()
        self.data = self._load_data()
        
        # Для текстового файла
        self.text_lines = []
    
    def _load_data(self) -> Dict:
        """Загрузить JSON с результатами"""
        if not self.json_path.exists():
            raise FileNotFoundError(f"Файл не найден: {self.json_path}")
        
        with open(self.json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _print_and_save(self, text: str, style: str = ""):
        """Вывести в консоль и сохранить в текстовый буфер"""
        if style:
            self.console.print(text, style=style)
        else:
            self.console.print(text)
        
        # Для текстового файла убираем Rich форматирование
        clean_text = text.replace("[bold]", "").replace("[/bold]", "")
        clean_text = clean_text.replace("[red]", "").replace("[/red]", "")
        clean_text = clean_text.replace("[green]", "").replace("[/green]", "")
        clean_text = clean_text.replace("[yellow]", "").replace("[/yellow]", "")
        clean_text = clean_text.replace("[cyan]", "").replace("[/cyan]", "")
        clean_text = clean_text.replace("[dim]", "").replace("[/dim]", "")
        self.text_lines.append(clean_text)
    
    def _add_separator(self, char="═", length=80):
        """Добавить разделитель"""
        line = char * length
        self._print_and_save(line)
    
    def run(self):
        """Генерировать полный отчёт"""
        self.console.clear()
        
        # 1. Заголовок
        self._generate_header()
        
        # 2. Общая сводка
        self._generate_summary()
        
        # 3. Одиночные атаки
        self._generate_single_turn_section()
        
        # 4. Цепочки атак
        self._generate_multi_turn_section()
        
        # 5. Оценка по типам
        self._generate_assessment_by_type()
        
        # 6. Рекомендации
        self._generate_recommendations()
        
        # 7. Сохранить текстовый отчёт
        self._save_text_report()
    
    def _generate_header(self):
        """Заголовок отчёта"""
        test_id = self.data.get('test_id', 'unknown')
        started_at = self.data.get('started_at', '')
        
        if started_at:
            try:
                dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                date_str = dt.strftime("%d %B %Y, %H:%M")
            except:
                date_str = started_at
        else:
            date_str = "Дата неизвестна"
        
        self._add_separator()
        self._print_and_save(f"   ОТЧЁТ О БЕЗОПАСНОСТИ АГЕНТА", "bold cyan")
        self._print_and_save(f"   Тест: {test_id}")
        self._print_and_save(f"   Дата: {date_str}")
        self._add_separator()
        self._print_and_save("")
    
    def _generate_summary(self):
        """Общая сводка"""
        summary = self.data.get('summary', {})
        
        total_attacks = summary.get('total_attacks_sent', 0)
        total_leaked = summary.get('total_leaked', 0)
        exploitation_rate = summary.get('exploitation_rate', 0)
        resistance_score = summary.get('overall_resistance_score', 0)
        
        self._print_and_save("1. ОБЩАЯ СВОДКА", "bold")
        self._print_and_save("   " + "─" * 50)
        self._print_and_save(f"   Агент: {self.data.get('target_url', 'unknown')}")
        self._print_and_save(f"   Длительность теста: {self.data.get('duration_seconds', 0):.1f} сек")
        self._print_and_save(f"   Всего атак: {total_attacks}")
        self._print_and_save(f"   Выявлено уязвимостей: {total_leaked} из {total_attacks} ({exploitation_rate:.1f}%)")
        
        # Оценка безопасности
        if resistance_score >= ResistanceLevel.EXCELLENT:
            level = "ОТЛИЧНЫЙ УРОВЕНЬ 🟢"
            color = "green"
        elif resistance_score >= ResistanceLevel.GOOD:
            level = "ХОРОШИЙ УРОВЕНЬ 🟡"
            color = "yellow"
        elif resistance_score >= ResistanceLevel.FAIR:
            level = "СРЕДНИЙ УРОВЕНЬ 🟠"
            color = "yellow"
        else:
            level = "НИЗКИЙ УРОВЕНЬ 🔴"
            color = "red"
        
        self._print_and_save(f"   Оценка защищённости: {resistance_score:.0f}/100 — {level}", color)
        self._print_and_save("")
    
    def _generate_single_turn_section(self):
        """Секция одиночных атак"""
        single_turn = self.data.get('single_turn')
        if not single_turn:
            return
        
        executions = single_turn.get('executions', [])
        if not executions:
            return
        
        # Подсчёт успешных атак
        successful = [e for e in executions if e.get('is_successful') == True]
        total = len(executions)
        errors = len([e for e in executions if e.get('error')])
        
        self._print_and_save("2. ОДИНОЧНЫЕ АТАКИ", "bold")
        self._print_and_save("   " + "─" * 50)
        self._print_and_save(f"   Отправлено: {total}  |  Ошибок: {errors}  |  Avg RT: {single_turn.get('avg_response_time', 0):.1f}s")
        self._print_and_save("")
        self._print_and_save(f"   ✅ Успешно заблокировано: {total - len(successful) - errors}")
        self._print_and_save(f"   🔴 Реализовавшихся атак: {len(successful)}", "red")
        self._print_and_save("")
        
        # Выводим КАЖДУЮ реализовавшуюся атаку ПОЛНОСТЬЮ
        if successful:
            for i, attack in enumerate(successful, 1):
                self._print_single_attack(i, attack)
        else:
            self._print_and_save("   ✅ Все одиночные атаки были успешно заблокированы!", "green")
            self._print_and_save("")
    
    def _print_single_attack(self, num: int, attack: Dict):
        """Вывести одну реализовавшуюся атаку ПОЛНОСТЬЮ"""
        attack_type = attack.get('attack_type', 'unknown')
        technique = attack.get('technique', 'unknown')
        payload = attack.get('payload', '')
        response = attack.get('response', '')
        analysis = attack.get('analysis', {})
        reason = analysis.get('reason', 'Причина не указана')
        
        attack_type_ru = ATTACK_TYPE_RU.get(attack_type, attack_type)
        technique_ru = TECHNIQUE_RU.get(technique, technique)
        
        self._print_and_save(f"   🔴 РЕАЛИЗОВАВШАЯСЯ АТАКА #{num}", "bold red")
        self._print_and_save(f"   Тип: {attack_type_ru}")
        self._print_and_save(f"   Техника: {technique_ru}")
        self._print_and_save("")
        
        # ПОЛНЫЙ payload БЕЗ СОКРАЩЕНИЙ
        self._print_and_save(f"   Запрос атакующего:", "yellow")
        self._print_and_save(f"   {payload}")
        self._print_and_save("")
        
        # ПОЛНЫЙ response БЕЗ СОКРАЩЕНИЙ
        self._print_and_save(f"   Ответ агента:", "red")
        self._print_and_save(f"   {response}")
        self._print_and_save("")
        
        # Вывод LLM-судьи
        self._print_and_save(f"   Вывод LLM-судьи:", "cyan")
        self._print_and_save(f"   {reason}")
        self._print_and_save("")
        self._print_and_save("   " + "─" * 50)
        self._print_and_save("")
    
    def _generate_multi_turn_section(self):
        """Секция цепочек атак"""
        multi_turn = self.data.get('multi_turn')
        if not multi_turn:
            return
        
        executions = multi_turn.get('executions', [])
        if not executions:
            return
        
        total_chains = multi_turn.get('total_chains', 0)
        total_steps = multi_turn.get('total_steps', 0)
        total_leaked = multi_turn.get('total_leaked_steps', 0)
        avg_resistance = multi_turn.get('avg_resistance_score', 0)
        
        self._print_and_save("3. ЦЕПОЧКИ АТАК (MULTI-TURN)", "bold")
        self._print_and_save("   " + "─" * 50)
        self._print_and_save(f"   Цепочек: {total_chains}  |  Шагов: {total_steps}  |  Утечек: {total_leaked}  |  Avg Resistance: {avg_resistance:.0f}/100")
        self._print_and_save("")
        
        # Сортируем по leak_rate (самые уязвимые первые)
        sorted_chains = sorted(executions, key=lambda x: x.get('leak_rate', 0), reverse=True)
        
        # Выводим КАЖДУЮ цепочку с утечками
        chains_with_leaks = [c for c in sorted_chains if c.get('leaked_steps', 0) > 0]
        
        if chains_with_leaks:
            self._print_and_save(f"   Обнаружено {len(chains_with_leaks)} уязвимых цепочек:", "red")
            self._print_and_save("")
            
            for i, chain in enumerate(chains_with_leaks, 1):
                self._print_chain(i, chain)
        else:
            self._print_and_save("   ✅ Все цепочки были успешно заблокированы!", "green")
            self._print_and_save("")
    
    def _print_chain(self, num: int, chain: Dict):
        """Вывести одну цепочку ПОЛНОСТЬЮ"""
        chain_id = chain.get('chain_id', 'unknown')
        total_steps = chain.get('total_steps', 0)
        leaked_steps = chain.get('leaked_steps', 0)
        leak_rate = chain.get('leak_rate', 0)
        resistance = chain.get('resistance_score', 0)
        first_leak = chain.get('first_leak_step')
        
        self._print_and_save(f"   🔴 ЦЕПОЧКА #{num} (Chain ID: {chain_id}) — resistance {resistance:.0f}/100", "bold red")
        self._print_and_save(f"   Утечек: {leaked_steps}/{total_steps} ({leak_rate:.1%})")
        if first_leak:
            self._print_and_save(f"   Первая утечка: шаг #{first_leak}")
        self._print_and_save("")
        
        # Выводим ВСЕ шаги ПОЛНОСТЬЮ
        steps = chain.get('steps', [])
        for step in steps:
            self._print_step(step, total_steps)
        
        self._print_and_save("   " + "─" * 50)
        self._print_and_save("")
    
    def _print_step(self, step: Dict, total_steps: int):
        """Вывести один шаг цепочки"""
        step_num = step.get('step_number', 0)
        phase = step.get('phase', 'unknown')
        payload = step.get('payload', '')
        response = step.get('response', '')
        leaked = step.get('leaked_data', False)
        severity = step.get('leak_severity', 'none')
        
        phase_ru = PHASE_RU.get(phase, phase)
        
        if leaked:
            marker = "⚠️"
            status = "УТЕЧКА"
            color = "red"
        else:
            marker = "✅"
            status = "норма"
            color = "green"
        
        self._print_and_save(f"      {marker} ШАГ {step_num}/{total_steps} ({phase_ru}) — {status}", color)
        
        # ПОЛНЫЙ payload
        self._print_and_save(f"      Запрос:", "yellow")
        self._print_and_save(f"      {payload}")
        
        # ПОЛНЫЙ response
        if response:
            if leaked:
                self._print_and_save(f"      Ответ агента (утечка {severity}):", "red")
            else:
                self._print_and_save(f"      Ответ агента:", "dim")
            self._print_and_save(f"      {response}")
        else:
            self._print_and_save(f"      ⚠️  Агент не ответил", "yellow")
        
        self._print_and_save("")
    
    def _generate_assessment_by_type(self):
        """Оценка по типам атак"""
        self._print_and_save("4. ОЦЕНКА ПО ТИПАМ АТАК", "bold")
        self._print_and_save("   " + "─" * 50)
        
        # Анализируем одиночные атаки
        single_turn = self.data.get('single_turn', {})
        executions = single_turn.get('executions', [])
        
        by_type = {}
        for e in executions:
            attack_type = e.get('attack_type', 'unknown')
            if attack_type not in by_type:
                by_type[attack_type] = {'total': 0, 'successful': 0}
            
            by_type[attack_type]['total'] += 1
            if e.get('is_successful'):
                by_type[attack_type]['successful'] += 1
        
        for attack_type, stats in by_type.items():
            total = stats['total']
            successful = stats['successful']
            blocked = total - successful
            resistance = (blocked / total * 100) if total > 0 else 0
            
            attack_type_ru = ATTACK_TYPE_RU.get(attack_type, attack_type)
            self._print_and_save(f"   {attack_type_ru}: устойчивость {resistance:.0f}% ({blocked}/{total})")
        
        # Multi-turn
        multi_turn = self.data.get('multi_turn', {})
        if multi_turn:
            avg_resistance = multi_turn.get('avg_resistance_score', 0)
            self._print_and_save(f"   Утечка данных (chains): устойчивость {avg_resistance:.0f}%")
        
        self._print_and_save("")
    
    def _generate_recommendations(self):
        """Рекомендации"""
        self._print_and_save("5. ВЫВОДЫ И РЕКОМЕНДАЦИИ", "bold")
        self._print_and_save("   " + "─" * 50)
        
        summary = self.data.get('summary', {})
        resistance = summary.get('overall_resistance_score', 0)
        exploitation_rate = summary.get('exploitation_rate', 0)
        
        # Автоматические выводы
        single_turn = self.data.get('single_turn', {})
        multi_turn = self.data.get('multi_turn', {})
        
        single_successful = len([e for e in single_turn.get('executions', []) if e.get('is_successful')])
        multi_leaked = multi_turn.get('total_leaked_steps', 0)
        
        if resistance >= ResistanceLevel.GOOD:
            self._print_and_save("   ✅ Агент демонстрирует хорошую защищённость", "green")
        else:
            self._print_and_save("   ⚠️  Агент уязвим к атакам", "yellow")
        
        if multi_leaked > 0:
            self._print_and_save("   ⚠️  Социальная инженерия работает после нескольких шагов диалога", "yellow")
        
        if single_successful > 0:
            self._print_and_save("   ⚠️  Обнаружены успешные одиночные атаки", "yellow")
        
        self._print_and_save("")
        self._print_and_save("   Рекомендации:", "cyan")
        
        if resistance < ResistanceLevel.GOOD:
            self._print_and_save("   • Усилить системный промпт")
            self._print_and_save("   • Добавить фильтрацию опасных запросов")
            self._print_and_save("   • Ограничить раскрытие внутренней информации")
        
        if multi_leaked > 0:
            self._print_and_save("   • Улучшить защиту от постепенной эскалации")
            self._print_and_save("   • Добавить обнаружение манипуляций в диалоге")
            self._print_and_save("   • Ограничить обсуждение внутреннего устройства агента")
        
        if resistance >= ResistanceLevel.GOOD and exploitation_rate < ExploitationLevel.MEDIUM:
            self._print_and_save("   ✅ Агент готов к продакшену", "green")
            self._print_and_save("   ✅ Продолжайте мониторинг в production", "green")
        
        self._print_and_save("")
        self._add_separator()
    
    def _save_text_report(self):
        """Сохранить текстовый отчёт рядом с JSON"""
        report_path = self.json_path.parent / f"{self.json_path.stem}_report.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.text_lines))
        
        self.console.print(f"\n💾 Текстовый отчёт сохранён: {report_path}", style="green")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python examples/run_report.py <path_to_labeled_json>")
        print("\nExample:")
        print("  python examples/run_report.py data/test_runs/hybrid_test_abc123_labeled.json")
        print("\nNOTE: Сначала запустите разметку:")
        print("  python -m core.attack_labeler data/test_runs/hybrid_test_abc123.json")
        return
    
    json_path = sys.argv[1]
    
    try:
        generator = ReportGenerator(json_path)
        generator.run()
        
        print("\n✅ Отчёт сгенерирован!")
        
    except FileNotFoundError as e:
        print(f"❌ {e}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
