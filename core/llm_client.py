"""
LLM Studio client for Agent-Breaker.
"""
import re
import json
import requests
from typing import Optional, Dict, Any, List


class LLMClient:
    """Client for interacting with LLM Studio API."""
    
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234",
        model: str = "gemma-3-12b-it",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: int = 60
    ):
        """
        Initialize LLM client.
        
        Args:
            base_url: LLM Studio base URL
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Send chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max_tokens
        
        Returns:
            Response text from LLM
        
        Raises:
            Exception: If request fails
        """
        url = f"{self.base_url}/v1/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            choices = data.get("choices")
            if not choices:
                raise ValueError(f"LLM returned no choices: {data}")
            return choices[0].get("message", {}).get("content", "")
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"LLM request failed: {e}")
    
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Send completion request (convenience method).
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Override default temperature
            max_tokens: Override default max_tokens
        
        Returns:
            Response text from LLM
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        return self.chat(messages, temperature, max_tokens)
    
    def analyze_code(
        self,
        code: str,
        filename: str,
        focus_areas: List[str]
    ) -> Dict[str, Any]:
        """
        Analyze code for security vulnerabilities.
        
        Args:
            code: Source code to analyze
            filename: Name of the file
            focus_areas: Areas to focus on (e.g., prompt_injection, toxicity)
        
        Returns:
            Analysis results as dict
        """
        system_prompt = """Ты эксперт по безопасности, анализирующий Python код на уязвимости в LLM-приложениях.

Твоя задача - найти проблемы безопасности, особенно:
- Prompt injection риски (OWASP LLM01)
- Риски генерации токсичного контента
- Проблемы валидации входных данных
- Проблемы фильтрации выходных данных
- Утечки данных

Отвечай ТОЛЬКО на русском языке. Предоставь детальный JSON ответ."""

        user_prompt = f"""Проанализируй этот Python файл на уязвимости безопасности.

Файл: {filename}

Области фокуса: {', '.join(focus_areas)}

Код:
```python
{code}
```

Предоставь анализ в формате JSON (ВСЕ ПОЛЯ НА РУССКОМ):
{{
  "vulnerabilities": [
    {{
      "type": "prompt_injection" | "toxicity_generation" | "input_validation" | "output_filtering" | "other",
      "severity": "critical" | "high" | "medium" | "low",
      "location": "номер_строки или имя_функции",
      "description": "подробное описание на русском",
      "code_snippet": "соответствующий код",
      "evidence": "почему это уязвимость (на русском)",
      "confidence": 0.0-1.0,
      "remediation": "как исправить (на русском)",
      "owasp_category": "OWASP LLM01" (если применимо)
    }}
  ],
  "summary": "общая оценка на русском",
  "risk_score": 0.0-10.0
}}

ВАЖНО: Выводи ТОЛЬКО валидный JSON, без markdown, без объяснений. ВСЕ ТЕКСТЫ НА РУССКОМ ЯЗЫКЕ."""

        try:
            response = self.complete(user_prompt, system_prompt, temperature=0.3)
            response = self.clean_json_response(response)
            result = json.loads(response)
            return result
            
        except json.JSONDecodeError as e:
            # If JSON parsing fails, return error
            return {
                "vulnerabilities": [],
                "summary": f"Failed to parse LLM response: {e}",
                "risk_score": 0.0,
                "error": str(e),
                "raw_response": response
            }
        except Exception as e:
            return {
                "vulnerabilities": [],
                "summary": f"Analysis failed: {e}",
                "risk_score": 0.0,
                "error": str(e)
            }
    
    def is_available(self) -> bool:
        """
        Check if LLM Studio is available.
        
        Returns:
            True if available, False otherwise
        """
        try:
            url = f"{self.base_url}/v1/models"
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def clean_json_response(response: str) -> str:
        """Strip markdown code fences from an LLM JSON response."""
        response = response.strip()
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if match:
            return match.group(1).strip()
        return response

    def get_models(self) -> List[str]:
        """
        Get list of available models.
        
        Returns:
            List of model names
        """
        try:
            url = f"{self.base_url}/v1/models"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            return [model["id"] for model in data.get("data", [])]
        except Exception:
            return []
