"""
Example: Run Code Analyzer from command line.

Usage:
    python examples/run_analyzer.py
"""
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.analysis import AnalysisConfig
from core.code_analyzer import CodeAnalyzer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint


def print_report(report):
    """Print analysis report in a nice format."""
    console = Console(width=120, soft_wrap=True)  # Увеличена ширина до 120
    
    # Header
    console.print("\n" + "="*70, style="bold blue")
    console.print("📊 ОТЧЕТ АНАЛИЗА КОДА", style="bold blue", justify="center")
    console.print("="*70 + "\n", style="bold blue")
    
    # Summary
    console.print(Panel.fit(
        f"[bold]Цель:[/bold] {report.target_path}\n"
        f"[bold]Файлов проанализировано:[/bold] {report.total_files}\n"
        f"[bold]Найдено уязвимостей:[/bold] {report.total_vulnerabilities}\n"
        f"[bold]Оценка риска:[/bold] {report.risk_score:.1f}/10\n"
        f"[bold]Длительность:[/bold] {report.analysis_duration_seconds:.1f}с",
        title="Сводка",
        border_style="green"
    ))
    
    # Vulnerabilities by severity
    if report.total_vulnerabilities > 0:
        severity_table = Table(title="\n📈 Уязвимости по серьезности")
        severity_table.add_column("Серьезность", style="cyan")
        severity_table.add_column("Количество", style="magenta")
        
        for severity, count in report.vulnerabilities_by_severity.items():
            if count > 0:
                emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "🔵"}.get(severity.value, "⚪")
                severity_names = {
                    "critical": "КРИТИЧЕСКАЯ",
                    "high": "ВЫСОКАЯ", 
                    "medium": "СРЕДНЯЯ",
                    "low": "НИЗКАЯ",
                    "info": "ИНФО"
                }
                severity_table.add_row(f"{emoji} {severity_names.get(severity.value, severity.value.upper())}", str(count))
        
        console.print(severity_table)
        
        # Vulnerabilities by type
        type_table = Table(title="\n🔍 Уязвимости по типу")
        type_table.add_column("Тип", style="cyan")
        type_table.add_column("Количество", style="magenta")
        
        type_names = {
            "prompt_injection": "Prompt Injection",
            "toxicity_generation": "Генерация токсичности",
            "input_validation": "Валидация входных данных",
            "output_filtering": "Фильтрация выходных данных",
            "data_leakage": "Утечка данных",
            "rate_limiting": "Ограничение скорости",
            "authentication": "Аутентификация"
        }
        
        for vuln_type, count in report.vulnerabilities_by_type.items():
            if count > 0:
                type_name = type_names.get(vuln_type.value, vuln_type.value.replace("_", " ").title())
                type_table.add_row(type_name, str(count))
        
        console.print(type_table)
        
        # Detailed vulnerabilities
        console.print("\n" + "="*70, style="bold yellow")
        console.print("⚠️  ДЕТАЛЬНЫЕ УЯЗВИМОСТИ", style="bold yellow")
        console.print("="*70 + "\n", style="bold yellow")
        
        for i, file_analysis in enumerate(report.analyzed_files, 1):
            if file_analysis.vulnerabilities:
                console.print(f"\n[bold cyan]{file_analysis.file_info.name}[/bold cyan]")
                console.print(f"  📄 {file_analysis.file_info.lines_of_code} строк, "
                            f"{file_analysis.file_info.functions_count} функций\n")
                
                for j, vuln in enumerate(file_analysis.vulnerabilities, 1):
                    emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(vuln.severity.value, "⚪")
                    
                    severity_names = {
                        "critical": "критическая",
                        "high": "высокая",
                        "medium": "средняя", 
                        "low": "низкая"
                    }
                    
                    type_names = {
                        "prompt_injection": "PROMPT INJECTION",
                        "toxicity_generation": "ГЕНЕРАЦИЯ ТОКСИЧНОСТИ",
                        "input_validation": "ВАЛИДАЦИЯ ВХОДНЫХ ДАННЫХ",
                        "output_filtering": "ФИЛЬТРАЦИЯ ВЫХОДНЫХ ДАННЫХ"
                    }
                    
                    console.print(f"  {emoji} [bold]{j}. {type_names.get(vuln.type.value, vuln.type.value.upper())}[/bold] ({severity_names.get(vuln.severity.value, vuln.severity.value)})")
                    console.print(f"     Локация: {vuln.location}")
                    console.print(f"     {vuln.description}")
                    
                    # Code snippet with syntax highlighting
                    if vuln.code_snippet:
                        console.print("\n     [bold yellow]Код:[/bold yellow]")
                        # Add slight indent for code
                        code_lines = vuln.code_snippet.split('\n')
                        for line in code_lines:
                            console.print(f"     {line}", style="dim")
                        console.print()
                    
                    if vuln.evidence:
                        # Показываем полностью без обрезания
                        console.print(f"     [bold]Доказательство:[/bold] {vuln.evidence}")
                    
                    if vuln.remediation:
                        console.print(f"     [green]Исправление:[/green] {vuln.remediation}")
                    
                    console.print()
    
    # Recommendations
    if report.recommendations:
        console.print("\n" + "="*70, style="bold green")
        console.print("💡 РЕКОМЕНДАЦИИ", style="bold green")
        console.print("="*70 + "\n", style="bold green")
        
        for i, rec in enumerate(report.recommendations, 1):
            console.print(f"{i}. {rec}")
    
    # Summary text
    console.print()
    console.print(Panel.fit(report.summary, title="Оценка", border_style="blue"))


def save_report_json(report, output_file="analysis_report.json"):
    """Save report to JSON file."""
    output_path = Path("data/reports") / output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report.model_dump(), f, indent=2, default=str, ensure_ascii=False)
    
    print(f"\n💾 Отчет сохранен: {output_path}")


def main():
    """Main function."""
    # Fix encoding for Windows stdout redirection
    import sys
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    console = Console()
    
    console.print("\n🚀 [bold]Agent-Breaker Анализатор кода[/bold]\n", style="blue")
    
    # Configuration
    config = AnalysisConfig(
        target_path="C:/Users/Nikita/Documents/Python Projects/chatbot-professor_v2/app",
        file_extensions=[".py"],
        exclude_dirs=["__pycache__", ".git", "venv", ".venv"],
        max_file_size_kb=500,
        llm_base_url="http://127.0.0.1:1234",
        llm_model="gemma-3-12b-it",
        llm_temperature=0.1,  # Очень низкая для стабильных результатов
        llm_max_tokens=3000  # Увеличено для детальных ответов
    )
    
    # Check LLM availability
    from core.llm_client import LLMClient
    llm = LLMClient(base_url=config.llm_base_url)
    
    if not llm.is_available():
        console.print("❌ [bold red]ERROR:[/bold red] LLM Studio is not available!", style="red")
        console.print(f"Please ensure LLM Studio is running on {config.llm_base_url}", style="yellow")
        return
    
    console.print("✅ LLM Studio connection OK\n", style="green")
    
    # Run analysis
    try:
        analyzer = CodeAnalyzer(config)
        report = analyzer.analyze()
        
        # Print report
        print_report(report)
        
        # Save to JSON
        save_report_json(report)
        
        # Summary
        console.print("\n" + "="*70, style="bold green")
        if report.total_vulnerabilities == 0:
            console.print("✅ Analysis complete - no vulnerabilities found!", style="bold green")
        else:
            console.print(f"⚠️  Analysis complete - found {report.total_vulnerabilities} vulnerabilities", 
                        style="bold yellow")
        console.print("="*70 + "\n", style="bold green")
        
    except Exception as e:
        console.print(f"\n❌ [bold red]ERROR:[/bold red] {e}", style="red")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
