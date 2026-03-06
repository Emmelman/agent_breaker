"""
Генерация multi-turn цепочек атак
"""
import sys
from pathlib import Path

# Добавляем корневую папку проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.multi_turn_generator_old import MultiTurnChainGenerator
from core.llm_client import LLMClient

# LLM клиент
llm = LLMClient(
    base_url="http://localhost:1234",
    model="local-model"
)

# Генератор
generator = MultiTurnChainGenerator(llm)

# 🆕 Создаем папку если не существует
chains_dir = Path("data/chains")
chains_dir.mkdir(parents=True, exist_ok=True)

# Генерируем 10 цепочек
print("\n🔗 Начинаем генерацию...")
chains = generator.generate_chains(num_chains=3)

# Сохраняем
filepath = chains_dir / "multi_turn_chains.json"
generator.save_chains(
    attack_set=chains,
    filepath=str(filepath)
)

print(f"\n✅ Готово! Создано {chains.total_chains} цепочек")
print(f"   Всего шагов: {chains.total_steps}")
print(f"   Все цепочки успешно сгенерированы!")
