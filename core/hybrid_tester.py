"""
Hybrid Stress Tester - combines Single-turn and Multi-turn testing.

Runs both attack types in sequence:
1. Single-turn attacks (parallel clients)
2. Multi-turn chains (sequential execution)
"""
import asyncio
import json
import traceback
from pathlib import Path
from typing import Optional
from datetime import datetime

from models.test import (
    TestConfiguration,
    TestStatus,
    HybridTestRun
)
from models.multi_turn import MultiTurnChain, ChainStep, ChainExecution, MultiTurnAttackSet
from core.stress_tester import StressTester
from core.http_client import HTTPAgentClient
from core.constants import generate_test_id, LEAK_DETECTION_KEYWORDS


class MultiTurnTester:
    """
    Multi-Turn Chain Tester.
    
    Executes conversation chains where each step builds on previous context.
    """
    
    def __init__(self, target_url: str, chains_file: str, step_delay: int = 2, chain_delay: int = 5):
        self.target_url = target_url
        self.chains_file = chains_file
        self.step_delay = step_delay
        self.chain_delay = chain_delay
        self.executions = []
    
    def load_chains(self) -> MultiTurnAttackSet:
        """Load chains from JSON file"""
        with open(self.chains_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        chains = []
        for chain_data in data['chains']:
            steps = [
                ChainStep(
                    step_number=s['step_number'],
                    phase=s['phase'],
                    payload=s['payload'],
                    expected_behavior=s.get('expected_behavior')
                )
                for s in chain_data['steps']
            ]
            
            chain = MultiTurnChain(
                chain_id=chain_data['chain_id'],
                name=chain_data['name'],
                description=chain_data['description'],
                attack_type=chain_data['attack_type'],
                technique=chain_data['technique'],
                target=chain_data['target'],
                steps=steps
            )
            chains.append(chain)
        
        return MultiTurnAttackSet(chains=chains)
    
    async def run_chain(self, chain: MultiTurnChain, http_client: HTTPAgentClient) -> ChainExecution:
        """Execute a single multi-turn chain"""
        conversation_id = None
        execution = ChainExecution(
            chain_id=chain.chain_id,
            conversation_id=""
        )
        
        for i, step in enumerate(chain.steps, 1):
            try:
                # Send message preserving conversation_id
                result = await http_client.send_message(
                    message=step.payload,
                    conversation_id=conversation_id
                )
                
                # Update conversation_id
                if result.get("conversation_id"):
                    conversation_id = result["conversation_id"]
                    if not execution.conversation_id:
                        execution.conversation_id = conversation_id
                
                # Save response
                step.response = result.get("response")
                
                # Simple leak detection
                if step.response:
                    response_lower = step.response.lower()
                    if any(keyword in response_lower for keyword in LEAK_DETECTION_KEYWORDS):
                        step.leaked_data = True
                        step.leak_severity = "medium"
                    else:
                        step.leaked_data = False
                        step.leak_severity = "none"
                else:
                    step.leaked_data = False
                    step.leak_severity = "none"
                
                execution.executed_steps.append(step)
                
                # Delay between steps
                await asyncio.sleep(self.step_delay)
                
            except Exception as e:
                step.response = f"ERROR: {e}"
                step.leaked_data = False
                execution.executed_steps.append(step)
                execution.stop_reason = "error"
                execution.stopped_at_step = i
                break
        
        # Calculate metrics
        execution.completed = (execution.stop_reason != "error")
        execution.total_steps = len(execution.executed_steps)
        execution.leaked_steps = sum(1 for s in execution.executed_steps if s.leaked_data)
        execution.leak_rate = execution.leaked_steps / execution.total_steps if execution.total_steps > 0 else 0
        
        # First leak
        for step in execution.executed_steps:
            if step.leaked_data:
                execution.first_leak_step = step.step_number
                break
        
        # Resistance score
        execution.resistance_score = 100 - (execution.leak_rate * 100)
        
        return execution
    
    async def run_all(self, attack_set: MultiTurnAttackSet) -> dict:
        """Run all chains and return results"""
        print("\n🔗 Запуск Multi-Turn цепочек...")
        print(f"   Цепочек: {len(attack_set.chains)}")
        print(f"   Шагов total: {sum(len(c.steps) for c in attack_set.chains)}")
        
        async with HTTPAgentClient(self.target_url, timeout=180) as client:
            for i, chain in enumerate(attack_set.chains, 1):
                print(f"\n   └─ Цепочка {i}/{len(attack_set.chains)}: {chain.name}")
                
                execution = await self.run_chain(chain, client)
                self.executions.append(execution)
                
                # Summary
                print(f"      ✅ {execution.total_steps} шагов, утечек: {execution.leaked_steps} ({execution.leak_rate:.1%})")
                
                # Delay between chains
                if i < len(attack_set.chains):
                    await asyncio.sleep(self.chain_delay)
        
        # Calculate summary
        total_steps = sum(e.total_steps for e in self.executions)
        total_leaked = sum(e.leaked_steps for e in self.executions)
        avg_leak_rate = total_leaked / total_steps if total_steps > 0 else 0
        avg_resistance = sum(e.resistance_score for e in self.executions) / len(self.executions) if self.executions else 0
        
        return {
            "total_chains": len(self.executions),
            "total_steps": total_steps,
            "total_leaked_steps": total_leaked,
            "avg_leak_rate": avg_leak_rate,
            "avg_resistance_score": avg_resistance,
            "executions": [
                {
                    "chain_id": e.chain_id,
                    "conversation_id": e.conversation_id,
                    "total_steps": e.total_steps,
                    "leaked_steps": e.leaked_steps,
                    "leak_rate": e.leak_rate,
                    "first_leak_step": e.first_leak_step,
                    "resistance_score": e.resistance_score,
                    "completed": e.completed,
                    "stop_reason": e.stop_reason,
                    # Добавляем детализацию каждого шага
                    "steps": [
                        {
                            "step_number": s.step_number,
                            "phase": s.phase,
                            "payload": s.payload,
                            "response": s.response,
                            "leaked_data": s.leaked_data,
                            "leak_severity": s.leak_severity
                        }
                        for s in e.executed_steps
                    ]
                }
                for e in self.executions
            ]
        }


class HybridStressTester:
    """
    Hybrid Stress Tester.
    
    Combines:
    - Single-turn attacks (parallel stress testing)
    - Multi-turn chains (sequential conversation attacks)
    """
    
    def __init__(self, config: TestConfiguration):
        self.config = config
        self.test_run: Optional[HybridTestRun] = None
        
        # Initialize testers based on config
        self.single_tester = StressTester(config) if config.enable_single_turn else None
        
        self.multi_tester = None
        if config.enable_multi_turn and config.multi_turn_chains_file:
            self.multi_tester = MultiTurnTester(
                target_url=config.target_url,
                chains_file=config.multi_turn_chains_file,
                step_delay=config.multi_turn_step_delay,
                chain_delay=config.multi_turn_chain_delay
            )
    
    async def run(self) -> HybridTestRun:
        """
        Run hybrid test.
        
        Returns:
            HybridTestRun with combined results
        """
        print("="*70)
        print("🚀 HYBRID STRESS TEST")
        print("="*70)
        
        # Initialize test run
        test_id = generate_test_id()
        self.test_run = HybridTestRun(
            test_id=test_id,
            started_at=datetime.utcnow(),
            status=TestStatus.RUNNING,
            target_url=self.config.target_url,
            num_clients=self.config.num_clients,
            single_turn_enabled=self.config.enable_single_turn,
            multi_turn_enabled=self.config.enable_multi_turn
        )
        
        print(f"\n🎯 Конфигурация:")
        print(f"   - Target: {self.config.target_url}")
        print(f"   - Single-turn: {'✅' if self.config.enable_single_turn else '❌'}")
        print(f"   - Multi-turn: {'✅' if self.config.enable_multi_turn else '❌'}")
        
        try:
            # Phase 1: Single-turn attacks
            if self.single_tester:
                print("\n" + "="*70)
                print("📨 PHASE 1: SINGLE-TURN ATTACKS")
                print("="*70)
                
                single_results = await self.single_tester.run()
                self.test_run.single_turn_results = single_results
                
                print(f"\n✅ Single-turn завершен:")
                print(f"   - Запросов: {single_results.total_requests}")
                print(f"   - Успешных: {single_results.successful_requests}")
                print(f"   - Ошибок: {single_results.failed_requests}")
            
            # Phase 2: Multi-turn chains
            if self.multi_tester:
                print("\n" + "="*70)
                print("🔗 PHASE 2: MULTI-TURN CHAINS")
                print("="*70)
                
                # Load chains
                attack_set = self.multi_tester.load_chains()
                print(f"✅ Загружено {attack_set.total_chains} цепочек ({attack_set.total_steps} шагов)")
                
                # Run chains
                multi_results = await self.multi_tester.run_all(attack_set)
                self.test_run.multi_turn_results = multi_results
                
                print(f"\n✅ Multi-turn завершен:")
                print(f"   - Цепочек: {multi_results['total_chains']}")
                print(f"   - Шагов: {multi_results['total_steps']}")
                print(f"   - Утечек: {multi_results['total_leaked_steps']} ({multi_results['avg_leak_rate']:.1%})")
                print(f"   - Resistance Score: {multi_results['avg_resistance_score']:.1f}/100")
            
            self.test_run.status = TestStatus.COMPLETED
        
        except KeyboardInterrupt:
            print("\n\n⏹️  Тест остановлен пользователем")
            self.test_run.status = TestStatus.STOPPED
        
        except Exception as e:
            print(f"\n\n❌ ОШИБКА: {e}")
            traceback.print_exc()
            self.test_run.status = TestStatus.FAILED
        
        finally:
            self.test_run.completed_at = datetime.utcnow()
            self.test_run.calculate_summary()
        
        # Final summary
        print("\n" + "="*70)
        print("✅ HYBRID TEST COMPLETED")
        print("="*70)
        
        self._print_summary()
        
        return self.test_run
    
    def _print_summary(self):
        """Print combined summary"""
        print(f"\n📊 ИТОГОВАЯ СВОДКА:")
        print(f"   - Всего атак: {self.test_run.total_attacks_sent}")
        print(f"   - Успешных: {self.test_run.total_successful}")
        print(f"   - Ошибок: {self.test_run.total_failed}")
        print(f"   - Утечек: {self.test_run.total_leaked}")
        print(f"   - Avg Response Time: {self.test_run.avg_response_time:.2f}s")
        print(f"   - Duration: {self.test_run.duration_seconds:.1f}s")
        print(f"\n🛡️  БЕЗОПАСНОСТЬ:")
        print(f"   - Overall Resistance Score: {self.test_run.overall_resistance_score:.1f}/100")
        print(f"   - Exploitation Rate: {self.test_run.exploitation_rate:.1f}%")
    
    def save_results(self, output_dir: str = "data/test_runs") -> Path:
        """Save hybrid test results"""
        if not self.test_run:
            raise RuntimeError("No test run to save")
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = self.test_run.started_at.strftime("%Y%m%d_%H%M%S")
        filename = f"hybrid_test_{self.test_run.test_id}_{timestamp}.json"
        filepath = output_path / filename
        
        # Prepare data for JSON serialization
        data = {
            "test_id": self.test_run.test_id,
            "test_type": "hybrid",
            "started_at": self.test_run.started_at.isoformat(),
            "completed_at": self.test_run.completed_at.isoformat() if self.test_run.completed_at else None,
            "duration_seconds": self.test_run.duration_seconds,
            "status": self.test_run.status.value,
            
            # Config
            "target_url": self.test_run.target_url,
            "num_clients": self.test_run.num_clients,
            
            # Modes
            "single_turn_enabled": self.test_run.single_turn_enabled,
            "multi_turn_enabled": self.test_run.multi_turn_enabled,
            
            # Single-turn results
            "single_turn": self.test_run.single_turn_results.model_dump() if self.test_run.single_turn_results else None,
            
            # Multi-turn results
            "multi_turn": self.test_run.multi_turn_results,
            
            # Combined metrics
            "summary": {
                "total_attacks_sent": self.test_run.total_attacks_sent,
                "total_successful": self.test_run.total_successful,
                "total_failed": self.test_run.total_failed,
                "total_leaked": self.test_run.total_leaked,
                "avg_response_time": self.test_run.avg_response_time,
                "overall_resistance_score": self.test_run.overall_resistance_score,
                "exploitation_rate": self.test_run.exploitation_rate
            }
        }
        
        # Save
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n💾 Результаты сохранены: {filepath}")
        return filepath
