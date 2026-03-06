"""
HTTP client for communicating with target agent.
"""
import asyncio
import aiohttp
from typing import Optional, Dict, Any
import time


class HTTPAgentClient:
    """HTTP client for target LLM agent."""
    
    def __init__(
        self,
        api_url: str,
        timeout: int = 60,
        user_id: str = "stress_tester"
    ):
        """
        Initialize HTTP client.
        
        Args:
            api_url: API endpoint URL
            timeout: Request timeout in seconds
            user_id: User ID for requests
        """
        self.api_url = api_url
        self.timeout = timeout
        self.user_id = user_id
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def send_message(
        self,
        message: str,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send message to agent.
        
        Args:
            message: User message
            conversation_id: Optional conversation ID
        
        Returns:
            Response dict with keys: response, status_code, response_time, error
        """
        if not self.session:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        
        start_time = time.time()
        
        try:
            # Build request payload
            payload = {
                "user_id": self.user_id,
                "message": message
            }
            
            if conversation_id:
                payload["conversation_id"] = conversation_id
            
            # Send POST request
            async with self.session.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                response_time = time.time() - start_time
                status_code = response.status
                
                # Parse response
                if response.status == 200:
                    data = await response.json()
                    return {
                        "response": data.get("response", ""),
                        "conversation_id": data.get("conversation_id"),
                        "sources": data.get("sources", []),
                        "status_code": status_code,
                        "response_time": response_time,
                        "error": None
                    }
                else:
                    error_text = await response.text()
                    return {
                        "response": None,
                        "status_code": status_code,
                        "response_time": response_time,
                        "error": f"HTTP {status_code}: {error_text[:200]}"
                    }
        
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            return {
                "response": None,
                "status_code": None,
                "response_time": response_time,
                "error": f"Timeout after {self.timeout}s"
            }
        
        except aiohttp.ClientError as e:
            response_time = time.time() - start_time
            return {
                "response": None,
                "status_code": None,
                "response_time": response_time,
                "error": f"Client error: {str(e)}"
            }
        
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "response": None,
                "status_code": None,
                "response_time": response_time,
                "error": f"Unexpected error: {str(e)}"
            }
    
    async def health_check(self) -> bool:
        """
        Check if agent is healthy and responsive.
        
        Returns:
            True if agent is healthy, False otherwise
        """
        if not self.session:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        
        try:
            # Try to hit health endpoint
            health_url = self.api_url.replace("/api/chat", "/api/health")
            
            async with self.session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "healthy"
                return False
        
        except:
            # If health endpoint doesn't exist, try regular endpoint with simple message
            try:
                result = await self.send_message("Привет")
                return result["error"] is None
            except:
                return False
    
    @staticmethod
    def check_availability(api_url: str, timeout: int = 5) -> bool:
        """
        Synchronous check if API is available.
        
        Args:
            api_url: API endpoint URL
            timeout: Timeout in seconds
        
        Returns:
            True if available, False otherwise
        """
        import requests
        
        try:
            health_url = api_url.replace("/api/chat", "/api/health")
            response = requests.get(health_url, timeout=timeout)
            return response.status_code == 200
        except:
            # Try chat endpoint
            try:
                response = requests.post(
                    api_url,
                    json={"user_id": "test", "message": "test"},
                    timeout=timeout
                )
                return response.status_code in [200, 400]  # 400 also means API is up
            except:
                return False
