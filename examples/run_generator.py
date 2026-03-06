"""
Example: Run Attack Generator from command line.

Usage:
    python examples/run_generator.py
"""
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_client import LLMClient
from core.attack_generator import AttackGenerator
from models.analysis import CodeAnalysisReport
from rich.console import Console
from rich.table import Table
from rich.panel import Panel


def load_analysis_report(report_path: str) -> CodeAnalysisReport:
    """Load analysis report from JSON."""
    with open(report_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return CodeAnalysisReport(**data)


def display_attacks(attack_set, console):
    """Display generated attacks in a nice format."""
    console.print("\n" + "="*80, style="bold green")
    console.print("📋 СГЕНЕРИРОВАННЫЕ АТАКИ", style="bold green", justify="center")
    console.print("="*80 + "\n", style="bold green")
    
    # Summary
    console.print(Panel.fit(
        f"[bold]Всего атак:[/bold] {attack_set.total_attacks}\n"
        f"[bold]Prompt Injection:[/bold] {len(attack_set.prompt_injections)}\n"
        f"[bold]Toxicity тесты:[/bold] {len(attack_set.toxicity_tests)}\n"
        f"[bold]Оценка разнообразия:[/bold] {attack_set.diversity_score:.2f}/1.0",
        title="Сводка",
        border_style="green"
    ))
    
    # Prompt Injection examples
    console.print("\n📌 [bold cyan]Примеры Prompt Injection атак:[/bold cyan]\n")
    
    for i, attack in enumerate(attack_set.prompt_injections[:5], 1):
        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢"
        }.get(attack.severity.value, "⚪")
        
        console.print(f"{severity_emoji} [bold]{i}. [{attack.technique.value}][/bold]")
        console.print(f"   Payload: {attack.payload[:80]}...")
        console.print(f"   Ожидаемый результат: {attack.expected_outcome}")
        console.print()
    
    if len(attack_set.prompt_injections) > 5:
        console.print(f"   ... и еще {len(attack_set.prompt_injections) - 5} атак\n")
    
    # Toxicity examples
    console.print("\n🔥 [bold cyan]Примеры Toxicity тестов:[/bold cyan]\n")
    
    for i, test in enumerate(attack_set.toxicity_tests[:5], 1):
        risk_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢"
        }.get(test.expected_risk.value, "⚪")
        
        console.print(f"{risk_emoji} [bold]{i}. [{test.toxicity_type.value}][/bold]")
        console.print(f"   Prompt: {test.prompt[:80]}...")
        console.print()
    
    if len(attack_set.toxicity_tests) > 5:
        console.print(f"   ... и еще {len(attack_set.toxicity_tests) - 5} тестов\n")
    
    # Diversity stats
    console.print("\n" + "="*80, style="bold blue")
    console.print("📊 СТАТИСТИКА РАЗНООБРАЗИЯ", style="bold blue", justify="center")
    console.print("="*80 + "\n", style="bold blue")
    
    # Techniques distribution
    technique_counts = {}
    for attack in attack_set.prompt_injections:
        technique_counts[attack.technique.value] = technique_counts.get(attack.technique.value, 0) + 1
    
    table = Table(title="Распределение техник Prompt Injection")
    table.add_column("Техника", style="cyan")
    table.add_column("Количество", style="magenta")
    
    for technique, count in sorted(technique_counts.items(), key=lambda x: x[1], reverse=True):
        table.add_row(technique, str(count))
    
    console.print(table)
    
    # Toxicity types distribution
    toxicity_counts = {}
    for test in attack_set.toxicity_tests:
        toxicity_counts[test.toxicity_type.value] = toxicity_counts.get(test.toxicity_type.value, 0) + 1
    
    table2 = Table(title="\nРаспределение типов Toxicity")
    table2.add_column("Тип", style="cyan")
    table2.add_column("Количество", style="magenta")
    
    for tox_type, count in sorted(toxicity_counts.items(), key=lambda x: x[1], reverse=True):
        table2.add_row(tox_type, str(count))
    
    console.print(table2)


def main():
    """Main function."""
    # Fix encoding for Windows
    import sys
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    console = Console()
    
    console.print("\n🚀 [bold]Agent-Breaker Attack Generator[/bold]\n", style="blue")
    
    # Initialize LLM client
    llm_client = LLMClient(
        base_url="http://127.0.0.1:1234",
        model="gemma-3-12b-it",
        temperature=0.8,  # Higher for creativity
        max_tokens=4000
    )
    
    # Check LLM availability
    if not llm_client.is_available():
        console.print("❌ [bold red]ОШИБКА:[/bold red] LLM Studio недоступен!", style="red")
        console.print("Убедитесь что LLM Studio запущен на http://127.0.0.1:1234", style="yellow")
        return
    
    console.print("✅ LLM Studio подключен\n", style="green")
    
    # Try to load analysis report
    analysis_report = None
    report_path = Path("data/reports/analysis_report.json")
    
    if report_path.exists():
        try:
            console.print(f"📄 Загружаю отчет анализа: {report_path}", style="cyan")
            analysis_report = load_analysis_report(str(report_path))
            console.print(f"✅ Загружен отчет с {analysis_report.total_vulnerabilities} уязвимостями\n", style="green")
        except Exception as e:
            console.print(f"⚠️  Предупреждение: Не удалось загрузить отчет: {e}", style="yellow")
            console.print("Генерация атак будет без контекста уязвимостей\n", style="yellow")
    else:
        console.print("⚠️  Отчет анализа не найден. Генерация атак будет без контекста.\n", style="yellow")
        console.print(f"Для использования контекста запустите сначала: python examples/run_analyzer.py\n", style="dim")
    
    # Create generator
    generator = AttackGenerator(
        llm_client=llm_client,
        analysis_report=analysis_report,
        diversity_threshold=0.5
    )
    
    # Generate attacks
    try:
        attack_set = generator.generate_attack_set(
            prompt_injection_count=6,
            toxicity_count=6
        )
        
        # Save attacks
        console.print()
        generator.save_attack_set(attack_set, output_dir="data/attacks")
        
        # Display results
        display_attacks(attack_set, console)
        
        # Final summary
        console.print("\n" + "="*80, style="bold green")
        console.print("✅ Генерация завершена успешно!", style="bold green", justify="center")
        console.print("="*80 + "\n", style="bold green")
        
        console.print("📁 Атаки сохранены в:", style="cyan")
        console.print("   - data/attacks/prompt_injection_attacks.json")
        console.print("   - data/attacks/toxicity_tests.json")
        console.print("   - data/attacks/attack_set.json\n")
        
        console.print("🎯 Следующий шаг: Запустите генерацию последовательных атак examples/generate_multi_turn_chains.py\n", style="yellow")
        
    except Exception as e:
        console.print(f"\n❌ [bold red]ОШИБКА:[/bold red] {e}", style="red")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
