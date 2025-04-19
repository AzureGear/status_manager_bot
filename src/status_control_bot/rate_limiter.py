from collections import defaultdict, deque
import time

class RateLimiter:
    # Лимитирование сообщений в секунду
    def __init__(self, max_calls=3, time_frame=1.0):
        self.max_calls = max_calls
        self.time_frame = time_frame
        self.user_timestamps = defaultdict(deque)

    def check_rate_limit(self, user_id: int) -> bool:
        now = time.time()
        timestamps = self.user_timestamps[user_id]
        
        # Удаляем старые запросы (>1 секунды назад)
        while timestamps and now - timestamps[0] > self.time_frame:
            timestamps.popleft()
            
        if len(timestamps) >= self.max_calls:
            return False
        timestamps.append(now)
        return True