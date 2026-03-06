"""
Data models for code analysis results.
"""
from typing import List, Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class VulnerabilitySeverity(str, Enum):
    """Vulnerability severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnerabilityType(str, Enum):
    """Types of vulnerabilities."""
    PROMPT_INJECTION = "prompt_injection"
    TOXICITY_GENERATION = "toxicity_generation"
    DATA_LEAKAGE = "data_leakage"
    INPUT_VALIDATION = "input_validation"
    OUTPUT_FILTERING = "output_filtering"
    RATE_LIMITING = "rate_limiting"
    AUTHENTICATION = "authentication"
    OTHER = "other"


class FileInfo(BaseModel):
    """Information about analyzed file."""
    path: str
    name: str
    size_bytes: int
    lines_of_code: int
    functions_count: int
    classes_count: int


class Vulnerability(BaseModel):
    """Detected vulnerability."""
    type: VulnerabilityType
    severity: VulnerabilitySeverity
    location: str  # file:line
    description: str
    code_snippet: Optional[str] = None
    evidence: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    remediation: Optional[str] = None
    cwe_id: Optional[str] = None  # Common Weakness Enumeration ID
    owasp_category: Optional[str] = None  # e.g., "OWASP LLM01"


class FunctionAnalysis(BaseModel):
    """Analysis of a function."""
    name: str
    location: str
    parameters: List[str]
    calls_llm: bool
    accesses_database: bool
    handles_user_input: bool
    has_validation: bool
    vulnerabilities: List[Vulnerability] = []


class FileAnalysis(BaseModel):
    """Analysis results for a single file."""
    file_info: FileInfo
    functions: List[FunctionAnalysis]
    vulnerabilities: List[Vulnerability]
    imports: List[str]
    api_endpoints: List[Dict[str, Any]] = []  # For FastAPI routes
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class CodeAnalysisReport(BaseModel):
    """Complete code analysis report."""
    target_path: str
    analyzed_files: List[FileAnalysis]
    total_files: int
    total_vulnerabilities: int
    vulnerabilities_by_severity: Dict[VulnerabilitySeverity, int]
    vulnerabilities_by_type: Dict[VulnerabilityType, int]
    risk_score: float = Field(ge=0.0, le=10.0)  # Overall risk score 0-10
    summary: str
    recommendations: List[str] = []
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    analysis_duration_seconds: float = 0.0
    
    def get_high_severity_vulns(self) -> List[Vulnerability]:
        """Get all HIGH and CRITICAL severity vulnerabilities."""
        vulns = []
        for file_analysis in self.analyzed_files:
            vulns.extend([
                v for v in file_analysis.vulnerabilities 
                if v.severity in [VulnerabilitySeverity.HIGH, VulnerabilitySeverity.CRITICAL]
            ])
        return vulns
    
    def get_vulns_by_type(self, vuln_type: VulnerabilityType) -> List[Vulnerability]:
        """Get vulnerabilities of specific type."""
        vulns = []
        for file_analysis in self.analyzed_files:
            vulns.extend([
                v for v in file_analysis.vulnerabilities 
                if v.type == vuln_type
            ])
        return vulns
    
    def calculate_risk_score(self) -> float:
        """Calculate overall risk score (0-10)."""
        if self.total_vulnerabilities == 0:
            return 0.0
        
        # Weight by severity
        weights = {
            VulnerabilitySeverity.CRITICAL: 4.0,
            VulnerabilitySeverity.HIGH: 3.0,
            VulnerabilitySeverity.MEDIUM: 2.0,
            VulnerabilitySeverity.LOW: 1.0,
            VulnerabilitySeverity.INFO: 0.5
        }
        
        total_score = sum(
            self.vulnerabilities_by_severity.get(severity, 0) * weight
            for severity, weight in weights.items()
        )
        
        # Normalize to 0-10 scale
        max_possible = self.total_vulnerabilities * 4.0
        if max_possible == 0:
            return 0.0
        
        return min(10.0, (total_score / max_possible) * 10.0)


class AnalysisConfig(BaseModel):
    """Configuration for code analysis."""
    target_path: str
    file_extensions: List[str] = [".py"]
    exclude_dirs: List[str] = ["__pycache__", ".git", "venv"]
    max_file_size_kb: int = 500
    llm_provider: str = "llm_studio"
    llm_base_url: str = "http://127.0.0.1:1234"
    llm_model: str = "gemma-3-12b-it"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2000
