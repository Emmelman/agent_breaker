"""
Code Analyzer - analyzes target application code for vulnerabilities.
"""
import time
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

from models.analysis import (
    FileAnalysis,
    FunctionAnalysis,
    Vulnerability,
    VulnerabilitySeverity,
    VulnerabilityType,
    CodeAnalysisReport,
    AnalysisConfig
)
from core.file_reader import FileReader
from core.llm_client import LLMClient


class CodeAnalyzer:
    """Analyze source code for security vulnerabilities using LLM."""
    
    def __init__(self, config: AnalysisConfig):
        """
        Initialize code analyzer.
        
        Args:
            config: Analysis configuration
        """
        self.config = config
        self.file_reader = FileReader(
            target_path=config.target_path,
            file_extensions=config.file_extensions,
            exclude_dirs=config.exclude_dirs,
            max_file_size_kb=config.max_file_size_kb
        )
        self.llm_client = LLMClient(
            base_url=config.llm_base_url,
            model=config.llm_model,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens
        )
    
    def analyze(self) -> CodeAnalysisReport:
        """
        Analyze all files in target path.
        
        Returns:
            CodeAnalysisReport with findings
        """
        start_time = time.time()
        
        print(f"🔍 Starting code analysis of: {self.config.target_path}")
        print(f"📂 Finding Python files...")
        
        # Find all files
        files = self.file_reader.find_files()
        print(f"✅ Found {len(files)} Python files")
        
        # Analyze each file
        analyzed_files = []
        for i, file_path in enumerate(files, 1):
            print(f"\n[{i}/{len(files)}] Analyzing: {file_path.name}")
            
            try:
                file_analysis = self._analyze_file(file_path)
                analyzed_files.append(file_analysis)
                
                # Print vulnerabilities found
                if file_analysis.vulnerabilities:
                    print(f"  ⚠️  Found {len(file_analysis.vulnerabilities)} vulnerabilities")
                    for vuln in file_analysis.vulnerabilities:
                        print(f"     - {vuln.severity.upper()}: {vuln.type}")
                else:
                    print(f"  ✅ No vulnerabilities detected")
                    
            except Exception as e:
                print(f"  ❌ Error analyzing {file_path.name}: {e}")
        
        # Generate report
        report = self._generate_report(analyzed_files)
        report.analysis_duration_seconds = time.time() - start_time
        
        print(f"\n" + "="*60)
        print(f"📊 ANALYSIS COMPLETE")
        print(f"="*60)
        print(f"Files analyzed: {report.total_files}")
        print(f"Vulnerabilities found: {report.total_vulnerabilities}")
        print(f"Risk score: {report.risk_score:.1f}/10")
        print(f"Duration: {report.analysis_duration_seconds:.1f}s")
        print(f"="*60)
        
        return report
    
    def _analyze_file(self, file_path: Path) -> FileAnalysis:
        """
        Analyze a single file.
        
        Args:
            file_path: Path to file
        
        Returns:
            FileAnalysis object
        """
        # Get file info
        file_info = self.file_reader.get_file_info(file_path)
        
        # Read code
        code = self.file_reader.read_file(file_path)
        
        # Parse AST
        tree = self.file_reader.parse_ast(code)
        if not tree:
            return FileAnalysis(
                file_info=file_info,
                functions=[],
                vulnerabilities=[],
                imports=[],
                api_endpoints=[]
            )
        
        # Extract structure
        functions_info = self.file_reader.extract_functions(tree)
        imports = self.file_reader.extract_imports(tree)
        api_endpoints = self.file_reader.extract_api_endpoints(tree, code)
        
        # Analyze with LLM
        print(f"  🤖 Analyzing with LLM...")
        llm_result = self.llm_client.analyze_code(
            code=code,
            filename=file_path.name,
            focus_areas=["prompt_injection", "toxicity_generation", "input_validation"]
        )
        
        # Parse vulnerabilities from LLM response
        vulnerabilities = self._parse_llm_vulnerabilities(
            llm_result.get("vulnerabilities", []),
            file_path.name
        )
        
        # Analyze functions
        function_analyses = []
        for func_info in functions_info:
            security_flags = self.file_reader.analyze_function_security(func_info)
            
            # Check if this function has vulnerabilities
            func_vulns = [
                v for v in vulnerabilities 
                if func_info["name"] in v.location
            ]
            
            function_analyses.append(FunctionAnalysis(
                name=func_info["name"],
                location=f"{file_path.name}:{func_info['line']}",
                parameters=func_info["parameters"],
                calls_llm=security_flags["calls_llm"],
                accesses_database=security_flags["accesses_database"],
                handles_user_input=security_flags["handles_user_input"],
                has_validation=security_flags["has_validation"],
                vulnerabilities=func_vulns
            ))
        
        return FileAnalysis(
            file_info=file_info,
            functions=function_analyses,
            vulnerabilities=vulnerabilities,
            imports=imports,
            api_endpoints=api_endpoints
        )
    
    def _parse_llm_vulnerabilities(
        self,
        llm_vulns: List[Dict[str, Any]],
        filename: str
    ) -> List[Vulnerability]:
        """
        Parse vulnerabilities from LLM response.
        
        Args:
            llm_vulns: List of vulnerability dicts from LLM
            filename: Name of file being analyzed
        
        Returns:
            List of Vulnerability objects
        """
        vulnerabilities = []
        
        for vuln_data in llm_vulns:
            try:
                # Map type
                vuln_type_str = vuln_data.get("type", "other")
                vuln_type = self._map_vulnerability_type(vuln_type_str)
                
                # Map severity
                severity_str = vuln_data.get("severity", "medium")
                severity = VulnerabilitySeverity(severity_str.lower())
                
                # Build location
                location = vuln_data.get("location", "unknown")
                if not location.startswith(filename):
                    location = f"{filename}:{location}"
                
                vulnerability = Vulnerability(
                    type=vuln_type,
                    severity=severity,
                    location=location,
                    description=vuln_data.get("description", "No description provided"),
                    code_snippet=vuln_data.get("code_snippet"),
                    evidence=vuln_data.get("evidence"),
                    confidence=float(vuln_data.get("confidence", 0.7)),
                    remediation=vuln_data.get("remediation"),
                    owasp_category=vuln_data.get("owasp_category")
                )
                
                vulnerabilities.append(vulnerability)
                
            except Exception as e:
                print(f"  ⚠️  Warning: Failed to parse vulnerability: {e}")
                continue
        
        return vulnerabilities
    
    def _map_vulnerability_type(self, type_str: str) -> VulnerabilityType:
        """Map string type to VulnerabilityType enum."""
        type_mapping = {
            "prompt_injection": VulnerabilityType.PROMPT_INJECTION,
            "toxicity_generation": VulnerabilityType.TOXICITY_GENERATION,
            "toxicity": VulnerabilityType.TOXICITY_GENERATION,
            "data_leakage": VulnerabilityType.DATA_LEAKAGE,
            "input_validation": VulnerabilityType.INPUT_VALIDATION,
            "output_filtering": VulnerabilityType.OUTPUT_FILTERING,
            "rate_limiting": VulnerabilityType.RATE_LIMITING,
            "authentication": VulnerabilityType.AUTHENTICATION,
        }
        
        return type_mapping.get(type_str.lower(), VulnerabilityType.OTHER)
    
    def _generate_report(self, analyzed_files: List[FileAnalysis]) -> CodeAnalysisReport:
        """
        Generate final analysis report.
        
        Args:
            analyzed_files: List of analyzed files
        
        Returns:
            CodeAnalysisReport
        """
        # Collect all vulnerabilities
        all_vulnerabilities = []
        for file_analysis in analyzed_files:
            all_vulnerabilities.extend(file_analysis.vulnerabilities)
        
        # Count by severity
        vulns_by_severity = {}
        for severity in VulnerabilitySeverity:
            vulns_by_severity[severity] = len([
                v for v in all_vulnerabilities if v.severity == severity
            ])
        
        # Count by type
        vulns_by_type = {}
        for vuln_type in VulnerabilityType:
            vulns_by_type[vuln_type] = len([
                v for v in all_vulnerabilities if v.type == vuln_type
            ])
        
        # Generate summary
        summary = self._generate_summary(all_vulnerabilities)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(all_vulnerabilities)
        
        # Create report
        report = CodeAnalysisReport(
            target_path=str(self.config.target_path),
            analyzed_files=analyzed_files,
            total_files=len(analyzed_files),
            total_vulnerabilities=len(all_vulnerabilities),
            vulnerabilities_by_severity=vulns_by_severity,
            vulnerabilities_by_type=vulns_by_type,
            risk_score=0.0,  # Will be calculated
            summary=summary,
            recommendations=recommendations
        )
        
        # Calculate risk score
        report.risk_score = report.calculate_risk_score()
        
        return report
    
    def _generate_summary(self, vulnerabilities: List[Vulnerability]) -> str:
        """Generate summary text."""
        if not vulnerabilities:
            return "В проанализированном коде не обнаружено уязвимостей безопасности."
        
        high_severity = len([v for v in vulnerabilities if v.severity in [
            VulnerabilitySeverity.HIGH, VulnerabilitySeverity.CRITICAL
        ]])
        
        summary = f"Найдено {len(vulnerabilities)} уязвимостей безопасности"
        if high_severity > 0:
            summary += f", включая {high_severity} высокой/критической серьезности"
        summary += ". "
        
        # Most common types
        type_counts = {}
        for v in vulnerabilities:
            type_counts[v.type] = type_counts.get(v.type, 0) + 1
        
        if type_counts:
            most_common = max(type_counts.items(), key=lambda x: x[1])
            type_names = {
                VulnerabilityType.PROMPT_INJECTION: "Prompt Injection",
                VulnerabilityType.TOXICITY_GENERATION: "генерация токсичности",
                VulnerabilityType.INPUT_VALIDATION: "валидация входных данных",
                VulnerabilityType.OUTPUT_FILTERING: "фильтрация выходных данных"
            }
            type_name = type_names.get(most_common[0], most_common[0].value)
            summary += f"Наиболее частая проблема: {type_name} ({most_common[1]} случаев)."
        
        return summary
    
    def _generate_recommendations(self, vulnerabilities: List[Vulnerability]) -> List[str]:
        """Generate recommendations based on findings."""
        recommendations = []
        
        # Check for prompt injection
        if any(v.type == VulnerabilityType.PROMPT_INJECTION for v in vulnerabilities):
            recommendations.append(
                "Реализуйте санитизацию и валидацию входных данных для всех пользовательских вводов, передаваемых в LLM"
            )
            recommendations.append(
                "Используйте разделители и четкие инструкции для отделения пользовательского ввода от системных промптов"
            )
        
        # Check for toxicity
        if any(v.type == VulnerabilityType.TOXICITY_GENERATION for v in vulnerabilities):
            recommendations.append(
                "Добавьте фильтрацию выходных данных для обнаружения и блокировки токсичного или вредоносного контента"
            )
            recommendations.append(
                "Реализуйте модерацию контента с использованием специализированных моделей или API"
            )
        
        # Check for input validation
        if any(v.type == VulnerabilityType.INPUT_VALIDATION for v in vulnerabilities):
            recommendations.append(
                "Добавьте комплексную валидацию входных данных для всех API endpoints"
            )
        
        # General recommendations
        if vulnerabilities:
            recommendations.append(
                "Проводите регулярные аудиты безопасности и пентестинг"
            )
            recommendations.append(
                "Реализуйте ограничение скорости (rate limiting) и мониторинг для API endpoints"
            )
        
        return recommendations
