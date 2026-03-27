import redis.asyncio as redis
import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisMemoryManager:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        self.session_ttl = 3600  # 1 hour TTL

    async def init_session(self, session_id: str, initial_context: dict):
        key = f"session:{session_id}"
        await self.redis.set(key, json.dumps(initial_context), ex=self.session_ttl)
        logger.info(f"Initialized Redis session {session_id}")

    async def get_session(self, session_id: str):
        key = f"session:{session_id}"
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def update_session(self, session_id: str, updates: dict):
        key = f"session:{session_id}"
        current = await self.get_session(session_id) or {}
        current.update(updates)
        await self.redis.set(key, json.dumps(current), ex=self.session_ttl)

memory_manager = RedisMemoryManager()
