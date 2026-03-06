"""
Stress Tester - bombards target agent with attacks.
"""
import asyncio
import json
import random
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Callable
from datetime import datetime, timedelta
from models.multi_turn import MultiTurnChain, ChainExecution
from models.attack import AttackSet, PromptInjectionAttack, ToxicityTest
from models.test import (
    TestMode,
    TestStatus,
    TestConfiguration,
    TestRun,
    AttackExecution,
    ClientStats,
    TestProgress,
    LiveEvent
)
from core.http_client import HTTPAgentClient


class StressTester:
    """Stress tester for LLM agents."""
    
    def __init__(self, config: TestConfiguration):
        """
        Initialize stress tester.
        
        Args:
            config: Test configuration
        """
        self.config = config
        self.test_run: Optional[TestRun] = None
        self.is_running = False
        self.stop_requested = False
        
        # Callbacks for live updates
        self.progress_callback: Optional[Callable[[TestProgress], None]] = None
        self.event_callback: Optional[Callable[[LiveEvent], None]] = None
    
    def set_progress_callback(self, callback: Callable[[TestProgress], None]):
        """Set callback for progress updates."""
        self.progress_callback = callback
    
    def set_event_callback(self, callback: Callable[[LiveEvent], None]):
        """Set callback for live events."""
        self.event_callback = callback
    
    def load_attacks(self) -> AttackSet:
        """Load attacks from file."""
        attacks_path = Path(self.config.attacks_file)
        
        if not attacks_path.exists():
            raise FileNotFoundError(f"Attacks file not found: {attacks_path}")
        
        with open(attacks_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return AttackSet(**data)
    
    async def run(self) -> TestRun:
        """
        Run stress test.
        
        Returns:
            TestRun with results
        """
        print("="*70)
        print("🚀 ЗАПУСК СТРЕСС-ТЕСТА")
        print("="*70)
        
        # Load attacks
        print(f"\n📂 Загрузка атак из {self.config.attacks_file}...")
        attack_set = self.load_attacks()
        print(f"✅ Загружено {attack_set.total_attacks} атак")
        print(f"   - Prompt Injection: {len(attack_set.prompt_injections)}")
        print(f"   - Toxicity тесты: {len(attack_set.toxicity_tests)}")
        
        # Initialize test run
        test_id = str(uuid.uuid4())[:8]
        self.test_run = TestRun(
            test_id=test_id,
            mode=self.config.mode,
            config=self.config,
            started_at=datetime.utcnow(),
            status=TestStatus.RUNNING
        )
        
        self.is_running = True
        self.stop_requested = False
        
        print(f"\n🎯 Конфигурация теста:")
        print(f"   - Режим: {self.config.mode.value}")
        print(f"   - Клиентов: {self.config.num_clients}")
        print(f"   - Атак всего: {attack_set.total_attacks}")
        print(f"   - Атак на клиента: ~{attack_set.total_attacks // self.config.num_clients}")
        print(f"   - Duration (soft limit): {self.config.duration_minutes} мин")
        print(f"   - Request timeout: {self.config.request_timeout}s")
        print(f"   - Rate limit: {self.config.rate_limit_per_client} req/s на клиента")
        print(f"   - Target: {self.config.target_url}")
        
        # Calculate estimated time
        attacks_per_client = attack_set.total_attacks // self.config.num_clients
        time_per_attack = 1.0 / self.config.rate_limit_per_client if self.config.rate_limit_per_client > 0 else 1.0
        estimated_send_time = attacks_per_client * time_per_attack
        print(f"\n⏱️  Оценка времени:")
        print(f"   - Минимум (только отправка): ~{int(estimated_send_time)}s")
        print(f"   - Реально (с ответами ~20s): ~{int(estimated_send_time + attacks_per_client * 20)}s ({(estimated_send_time + attacks_per_client * 20) / 60:.1f} мин)")
        print(f"   ⚠️  Duration={self.config.duration_minutes}мин - это мягкий лимит, тест продолжится если атаки не закончились")
        
        # Check target availability (HTTP mode)
        if self.config.mode == TestMode.HTTP:
            print(f"\n🔍 Проверка доступности агента...")
            if not HTTPAgentClient.check_availability(self.config.target_url):
                print(f"❌ ОШИБКА: Агент недоступен на {self.config.target_url}")
                print(f"   Убедитесь что агент запущен!")
                self.test_run.status = TestStatus.FAILED
                return self.test_run
            print(f"✅ Агент доступен")
        
        # Run test
        print(f"\n" + "="*70)
        print(f"🔥 НАЧИНАЕМ АТАКУ")
        print(f"="*70 + "\n")
        
        try:
            if self.config.mode == TestMode.HTTP:
                await self._run_http_test(attack_set)
            else:
                await self._run_emulated_test(attack_set)
            
            self.test_run.status = TestStatus.COMPLETED
        
        except KeyboardInterrupt:
            print("\n\n⏹️  Тест остановлен пользователем")
            self.test_run.status = TestStatus.STOPPED
        
        except Exception as e:
            print(f"\n\n❌ ОШИБКА: {e}")
            import traceback
            traceback.print_exc()
            self.test_run.status = TestStatus.FAILED
        
        finally:
            self.is_running = False
            self.test_run.completed_at = datetime.utcnow()
            self.test_run.calculate_summary()
        
        # Summary
        print("\n" + "="*70)
        print("✅ ТЕСТ ЗАВЕРШЕН")
        print("="*70)
        print(f"\n📊 Сводка:")
        print(f"   - Всего запросов: {self.test_run.total_requests}")
        print(f"   - Успешных: {self.test_run.successful_requests}")
        print(f"   - Ошибок: {self.test_run.failed_requests}")
        print(f"   - Средняя задержка: {self.test_run.avg_response_time:.2f}s")
        print(f"   - Длительность: {self.test_run.duration_seconds:.1f}s")
        
        return self.test_run
    
    async def _run_multi_turn_chain(
        self,
        chain: MultiTurnChain,
        http_client: HTTPAgentClient
    ) -> ChainExecution:
        """Выполнить multi-turn цепочку"""
        
        conversation_id = None
        execution = ChainExecution(
            chain_id=chain.chain_id,
            conversation_id=""
        )
        
        for step in chain.steps:
            # Отправляем шаг
            result = await http_client.send_message(
                message=step.payload,
                conversation_id=conversation_id  # ← СОХРАНЯЕМ!
            )
            
            # Обновляем conversation_id
            if result.get("conversation_id"):
                conversation_id = result["conversation_id"]
                if not execution.conversation_id:
                    execution.conversation_id = conversation_id
            
            # Сохраняем результат
            step.response = result.get("response")
            execution.executed_steps.append(step)
            
            # Задержка между шагами
            await asyncio.sleep(2)
        
        execution.completed = True
        execution.total_steps = len(execution.executed_steps)
        
        return execution

    async def _run_http_test(self, attack_set: AttackSet):
        """Run HTTP-based stress test."""
        # Prepare attack list
        all_attacks = attack_set.get_all_attacks()
        
        if self.config.randomize_attacks:
            random.shuffle(all_attacks)
        
        # Calculate how many attacks per client
        total_duration = self.config.duration_minutes * 60  # seconds
        attacks_per_client = len(all_attacks) // self.config.num_clients
        
        if attacks_per_client == 0:
            attacks_per_client = 1
            self.config.num_clients = len(all_attacks)
            print(f"⚠️  Скорректировано: {self.config.num_clients} клиентов")
        
        # Initialize client stats
        client_stats = [ClientStats(client_id=i) for i in range(self.config.num_clients)]
        self.test_run.client_stats = client_stats
        
        # Start time
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(minutes=self.config.duration_minutes)
        
        # Create HTTP client
        async with HTTPAgentClient(self.config.target_url, self.config.request_timeout) as client:
            # Create tasks for each client
            tasks = []
            for client_id in range(self.config.num_clients):
                # Assign attacks to this client
                start_idx = client_id * attacks_per_client
                
                # ✅ ДОБАВИТЬ ЭТИ СТРОКИ:
                # Last client gets all remaining attacks (handles rounding)
                if client_id == self.config.num_clients - 1:
                    end_idx = len(all_attacks)  # All remaining
                else:
                    end_idx = start_idx + attacks_per_client
                
                client_attacks = all_attacks[start_idx:end_idx]
                
                task = asyncio.create_task(
                    self._client_worker(
                        client_id=client_id,
                        attacks=client_attacks,
                        http_client=client,
                        end_time=end_time
                    )
                )
                tasks.append(task)
            
            # Progress monitoring task
            monitor_task = asyncio.create_task(
                self._monitor_progress(start_time, end_time, len(all_attacks))
            )
            
            # Wait for all clients to finish or timeout
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Cancel monitoring
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            # Cancel any remaining HTTP requests
            if client.session and not client.session.closed:
                # Give pending requests 5 seconds to complete
                print("\n\n⏳ Ожидание завершения pending запросов...")
                await asyncio.sleep(5)
    
    async def _client_worker(
        self,
        client_id: int,
        attacks: List[Dict],
        http_client: HTTPAgentClient,
        end_time: datetime
    ):
        """
        Worker for single client.
        
        Args:
            client_id: Client ID
            attacks: List of attacks for this client
            http_client: HTTP client instance
            end_time: When to stop (soft limit)
        """
        request_num = 0
        conversation_id = None  # Always None for independent attacks
        
        for attack in attacks:
            # Check if we should stop (user requested)
            if self.stop_requested:
                break
            
            # Soft timeout check (warn but continue)
            if datetime.utcnow() >= end_time:
                # Print warning only once per client
                if request_num == 0 or request_num % 5 == 0:
                    print(f"\n⚠️  Client {client_id}: Duration exceeded, but continuing to send all attacks...")
                # Continue anyway!
            
            request_num += 1
            
            # Send attack with retry logic
            retry_count = 0
            execution = None
            
            while retry_count <= self.config.retry_attempts:
                # IMPORTANT: Each attack is independent - no conversation_id!
                # This prevents context window overflow from accumulated history
                result = await http_client.send_message(
                    message=attack["payload"],
                    conversation_id=None  # ← ALWAYS None!
                )
                
                # Create execution record
                execution = AttackExecution(
                    attack_id=attack["id"],
                    attack_type=attack["type"],
                    payload=attack["payload"],
                    technique=attack["technique"],
                    client_id=client_id,
                    request_num=request_num,
                    response=result.get("response"),
                    status_code=result.get("status_code"),
                    response_time=result.get("response_time"),
                    error=result.get("error"),
                    retry_count=retry_count
                )
                
                # Check if we should retry
                should_retry = False
                if result.get("error"):
                    error_msg = result.get("error", "")
                    # Retry on timeout or 500 errors
                    if "Timeout" in error_msg or "HTTP 500" in error_msg or "HTTP 503" in error_msg:
                        should_retry = True
                
                # Break if success or max retries reached
                if not should_retry or retry_count >= self.config.retry_attempts:
                    break
                
                # Retry
                retry_count += 1
                print(f"\n🔄 Client {client_id}: Retry {retry_count}/{self.config.retry_attempts} for attack #{attack['id']}")
                await asyncio.sleep(2)  # Wait before retry
            
            # Save execution
            self.test_run.executions.append(execution)
            
            # Update client stats
            self.test_run.client_stats[client_id].update(execution)
            
            # Rate limiting
            if self.config.rate_limit_per_client > 0:
                await asyncio.sleep(1.0 / self.config.rate_limit_per_client)
    
    async def _monitor_progress(
        self,
        start_time: datetime,
        end_time: datetime,
        total_attacks: int
    ):
        """Monitor and report progress."""
        duration_exceeded_warned = False
        
        while self.is_running:
            await asyncio.sleep(2)  # Update every 2 seconds
            
            # Calculate progress
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            completed = len(self.test_run.executions)
            active = sum(1 for s in self.test_run.client_stats if s.requests_sent > 0)
            
            # Check if duration exceeded
            if datetime.utcnow() >= end_time and not duration_exceeded_warned:
                print(f"\n\n⏰ Planned duration exceeded, but continuing to send ALL attacks...")
                duration_exceeded_warned = True
            
            # Stop monitoring if all attacks sent
            if completed >= total_attacks:
                break
            
            # Calculate RPS
            rps = completed / elapsed if elapsed > 0 else 0
            
            # Calculate avg response time
            successful = [e for e in self.test_run.executions if not e.error and e.response_time]
            avg_rt = sum(e.response_time for e in successful) / len(successful) if successful else 0
            
            # Create progress object
            progress = TestProgress(
                status=TestStatus.RUNNING,
                started_at=start_time,
                elapsed_seconds=elapsed,
                total_attacks=total_attacks,
                completed_attacks=completed,
                progress_percent=0.0,
                total_clients=self.config.num_clients,
                active_clients=active,
                requests_per_second=rps,
                avg_response_time=avg_rt
            )
            progress.calculate_progress()
            
            # Call callback
            if self.progress_callback:
                self.progress_callback(progress)
            
            # Print progress
            self._print_progress(progress)
    
    def _print_progress(self, progress: TestProgress):
        """Print progress to console."""
        # Progress bar
        bar_length = 30
        filled = int(bar_length * progress.progress_percent / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        print(f"\r🔥 [{bar}] {progress.progress_percent:.1f}% | "
              f"⏱️ {progress.elapsed_seconds:.0f}s | "
              f"📨 {progress.completed_attacks} | "
              f"👥 {progress.active_clients}/{progress.total_clients} | "
              f"⚡ {progress.requests_per_second:.1f} req/s | "
              f"⏰ {progress.avg_response_time:.2f}s",
              end='', flush=True)
    
    async def _run_emulated_test(self, attack_set: AttackSet):
        """Run emulated stress test."""
        # TODO: Implement emulated mode
        raise NotImplementedError("Emulated mode will be implemented in Day 6")
    
    def stop(self):
        """Stop the test."""
        self.stop_requested = True
    
    def save_results(self, output_dir: str = "data/test_runs"):
        """Save test results to file."""
        if not self.test_run:
            raise RuntimeError("No test run to save")
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = self.test_run.started_at.strftime("%Y%m%d_%H%M%S")
        filename = f"test_run_{self.test_run.test_id}_{timestamp}.json"
        filepath = output_path / filename
        
        # Save
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(
                self.test_run.model_dump(),
                f,
                indent=2,
                ensure_ascii=False,
                default=str
            )
        
        print(f"\n💾 Результаты сохранены: {filepath}")
        return filepath
