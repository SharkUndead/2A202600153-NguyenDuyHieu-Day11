from collections import defaultdict, deque
import time
from google.adk.plugins import base_plugin
from google.genai import types

class RateLimitPlugin(base_plugin.BasePlugin):
    """
    Plugin to prevent abuse by limiting the number of requests a user can send 
    within a specific time window (Sliding Window Algorithm).
    
    Why: Prevents DoS attacks and manages API costs by blocking rapid-fire requests.
    """
    
    def __init__(self, max_requests=10, window_seconds=60):
        super().__init__(name="rate_limiter")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Dictionary mapping user_id -> deque of timestamps
        self.user_windows = defaultdict(deque)

    async def on_user_message_callback(self, *, invocation_context, user_message):
        """
        Check if the user has exceeded their request quota before sending to LLM.
        """
        # Default to "anonymous" if no user_id is provided in context
        user_id = getattr(invocation_context, 'user_id', 'anonymous')
        if not user_id:
            user_id = 'anonymous'
            
        now = time.time()
        window = self.user_windows[user_id]

        # 1. Clear expired timestamps from the front of the window
        while window and window[0] < (now - self.window_seconds):
            window.popleft()

        # 2. Check if the window is full
        if len(window) >= self.max_requests:
            wait_time = int(self.window_seconds - (now - window[0]))
            print(f"[RATE LIMIT] Blocked user '{user_id}'. Max {self.max_requests} requests per {self.window_seconds}s.")
            
            # Return a Content object that blocks the downstream execution
            return types.Content(
                parts=[types.Part.from_text(text=f"Rate limit exceeded. Please wait {wait_time} seconds before trying again.")],
                role="model"
            )

        # 3. Add current timestamp and allow
        window.append(now)
        return None  # Returning None allows the message to proceed to the next plugin/agent
