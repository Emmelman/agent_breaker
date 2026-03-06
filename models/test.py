"""
Data models for stress testing and results.
"""
from typing import List, Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class TestMode(str, Enum):
    """Test execution mode."""
    HTTP = "http"
    EMULATED = "emulated"


class TestStatus(str, Enum):
    """Test run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class AttackExecution(BaseModel):
    """Single attack execution result."""
    attack_id: int
    attack_type: str  # "prompt_injection" or "toxicity_test"
    payload: str
    technique: str
    
    # Execution details
    client_id: int
    request_num: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Response
    response: Optional[str] = None
    status_code: Optional[int] = None
    response_time: Optional[float] = None  # seconds
    
    # Error handling
    error: Optional[str] = None
    retry_count: int = 0
    
    # Analysis (will be filled by Response Analyzer later)
    is_successful: Optional[bool] = None  # Was attack successful?
    confidence: Optional[float] = None
    analysis: Optional[Dict[str, Any]] = None


class ClientStats(BaseModel):
    """Statistics for a single client."""
    client_id: int
    requests_sent: int = 0
    requests_successful: int = 0
    requests_failed: int = 0
    total_response_time: float = 0.0
    avg_response_time: float = 0.0
    
    def update(self, execution: AttackExecution):
        """Update stats with new execution."""
        self.requests_sent += 1
        
        if execution.error:
            self.requests_failed += 1
        else:
            self.requests_successful += 1
            if execution.response_time:
                self.total_response_time += execution.response_time
                self.avg_response_time = self.total_response_time / self.requests_successful


class TestProgress(BaseModel):
    """Real-time test progress."""
    status: TestStatus
    started_at: datetime
    elapsed_seconds: float
    
    # Progress
    total_attacks: int
    completed_attacks: int
    progress_percent: float
    
    # Clients
    total_clients: int
    active_clients: int
    
    # Performance
    requests_per_second: float
    avg_response_time: float
    
    # Live detections (filled during testing)
    detected_injections: int = 0
    detected_toxicity: int = 0
    
    def calculate_progress(self):
        """Calculate progress percentage."""
        if self.total_attacks > 0:
            self.progress_percent = (self.completed_attacks / self.total_attacks) * 100
        else:
            self.progress_percent = 0.0


class TestConfiguration(BaseModel):
    """Test run configuration."""
    # Mode
    mode: TestMode = TestMode.HTTP
    
    # Target
    target_url: Optional[str] = "http://localhost:8000/api/chat"
    target_code_path: Optional[str] = None  # For emulated mode
    
    # Attack source
    attacks_file: str = "data/attacks/attack_set.json"
    
    # Test parameters
    num_clients: int = 50
    duration_minutes: int = 3  # Soft limit - will continue if attacks remain
    request_timeout: int = 120  # Увеличено с 60 до 120 для медленных LLM
    retry_attempts: int = 3
    rate_limit_per_client: float = 10.0  # requests/second (can be fractional for slow rates)
    
    # Options
    randomize_attacks: bool = True
    save_responses: bool = True
    live_analysis: bool = False  # Analyze responses in real-time
    
    # 🆕 Hybrid Testing Mode
    enable_single_turn: bool = True  # Run single-turn attacks
    enable_multi_turn: bool = False  # Run multi-turn chain attacks
    multi_turn_chains_file: Optional[str] = None  # Path to chains JSON
    multi_turn_step_delay: int = 2  # Delay between steps in chain
    multi_turn_chain_delay: int = 5  # Delay between different chains


class TestRun(BaseModel):
    """Complete test run with results."""
    # Metadata
    test_id: str
    mode: TestMode
    config: TestConfiguration
    
    # Timing
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Status
    status: TestStatus = TestStatus.PENDING
    
    # Results
    executions: List[AttackExecution] = []
    client_stats: List[ClientStats] = []
    
    # Summary
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    
    # Analysis summary (filled later)
    successful_injections: int = 0
    successful_toxicity: int = 0
    total_vulnerabilities_exploited: int = 0
    
    def calculate_summary(self):
        """Calculate summary statistics."""
        self.total_requests = len(self.executions)
        
        successful = [e for e in self.executions if not e.error]
        self.successful_requests = len(successful)
        self.failed_requests = self.total_requests - self.successful_requests
        
        if successful:
            response_times = [e.response_time for e in successful if e.response_time]
            if response_times:
                self.avg_response_time = sum(response_times) / len(response_times)
        
        # Duration
        if self.completed_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()


class LiveEvent(BaseModel):
    """Live event during testing."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str  # "injection_detected", "toxicity_detected", "error", "milestone"
    severity: str  # "critical", "high", "medium", "low", "info"
    message: str
    details: Optional[Dict[str, Any]] = None


class TestReport(BaseModel):
    """Final test report."""
    test_run: TestRun
    
    # High-level metrics
    total_attacks_sent: int
    exploitation_rate: float  # Percentage of successful attacks
    
    # By type
    prompt_injection_stats: Dict[str, Any]
    toxicity_stats: Dict[str, Any]
    
    # Top findings
    critical_findings: List[Dict[str, Any]]
    high_findings: List[Dict[str, Any]]
    
    # Recommendations
    recommendations: List[str]
    
    # Risk assessment
    overall_risk_score: float  # 0-10
    risk_level: str  # "critical", "high", "medium", "low"
    
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class HybridTestRun(BaseModel):
    """
    Результаты гибридного тестирования (Single-turn + Multi-turn).
    
    Объединяет результаты обоих типов атак в единый отчет.
    """
    # Metadata
    test_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    status: TestStatus = TestStatus.PENDING
    
    # Configuration used
    target_url: str
    num_clients: int
    
    # Single-turn results
    single_turn_enabled: bool = False
    single_turn_results: Optional[TestRun] = None
    
    # Multi-turn results
    multi_turn_enabled: bool = False
    multi_turn_results: Optional[Dict[str, Any]] = None  # From MultiTurnTester
    
    # Combined metrics
    total_attacks_sent: int = 0  # Single + Multi-turn steps
    total_successful: int = 0
    total_failed: int = 0
    total_leaked: int = 0  # From multi-turn analysis
    
    # Performance
    avg_response_time: float = 0.0
    total_duration: float = 0.0
    
    # Security metrics
    overall_resistance_score: float = 0.0  # 0-100
    exploitation_rate: float = 0.0  # Percentage of successful attacks
    
    def calculate_summary(self):
        """Calculate combined summary metrics"""
        # Single-turn metrics
        if self.single_turn_results:
            self.total_attacks_sent += self.single_turn_results.total_requests
            self.total_successful += self.single_turn_results.successful_requests
            self.total_failed += self.single_turn_results.failed_requests
            
            if self.single_turn_results.avg_response_time:
                self.avg_response_time = self.single_turn_results.avg_response_time
        
        # Multi-turn metrics
        if self.multi_turn_results:
            total_steps = self.multi_turn_results.get("total_steps", 0)
            leaked_steps = self.multi_turn_results.get("total_leaked_steps", 0)
            avg_resistance = self.multi_turn_results.get("avg_resistance_score", 0)
            
            self.total_attacks_sent += total_steps
            self.total_leaked += leaked_steps
            
            # Calculate overall resistance
            if self.single_turn_enabled and self.multi_turn_enabled:
                # Weighted average based on attack counts
                single_weight = self.single_turn_results.total_requests if self.single_turn_results else 0
                multi_weight = total_steps
                total_weight = single_weight + multi_weight
                
                if total_weight > 0:
                    # Single-turn: assume 80% resistance (no leak detection yet)
                    # Multi-turn: use actual resistance score
                    single_resistance = 80.0
                    self.overall_resistance_score = (
                        (single_resistance * single_weight + avg_resistance * multi_weight) / total_weight
                    )
            elif self.multi_turn_enabled:
                self.overall_resistance_score = avg_resistance
            else:
                self.overall_resistance_score = 80.0  # Default for single-turn only
        
        # Exploitation rate
        if self.total_attacks_sent > 0:
            self.exploitation_rate = (self.total_leaked / self.total_attacks_sent) * 100
        
        # Duration
        if self.completed_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

