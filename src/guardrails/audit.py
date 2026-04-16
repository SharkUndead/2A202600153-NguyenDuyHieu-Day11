import json
import time
import os
from datetime import datetime
from google.adk.plugins import base_plugin

class AuditLogPlugin(base_plugin.BasePlugin):
    """
    Plugin to record every interaction for security compliance and monitoring.
    
    Why: Mandatory for production systems to detect attacks, audit agent behavior, 
    and identify which guardrails are triggering most frequently.
    """
    
    def __init__(self, filepath="audit_log.json"):
        super().__init__(name="audit_log")
        self.filepath = filepath
        self.logs = []
        # Store start times for latency calculation
        self._request_start_times = {}

    async def on_user_message_callback(self, *, invocation_context, user_message):
        """
        Record the start of a request.
        """
        request_id = getattr(invocation_context, 'request_id', id(invocation_context))
        self._request_start_times[request_id] = {
            "timestamp": datetime.now().isoformat(),
            "start_time": time.time(),
            "input": user_message.parts[0].text if user_message.parts else "",
            "user_id": getattr(invocation_context, 'user_id', 'student') 
        }
        return None  # Pass through

    async def after_model_callback(self, *, callback_context, llm_response):
        """
        Record the final response and calculate latency.
        """
        invocation_context = getattr(callback_context, 'invocation_context', None)
        request_id = getattr(invocation_context, 'request_id', id(invocation_context))
        
        if request_id not in self._request_start_times:
            # Fallback to the latest start time
            if not self._request_start_times:
                return llm_response
            request_id = list(self._request_start_times.keys())[-1]

        data = self._request_start_times.pop(request_id)
        latency_ms = int((time.time() - data.pop("start_time")) * 1000)
        
        output_text = llm_response.text if hasattr(llm_response, 'text') else str(llm_response)
        
        log_entry = {
            "timestamp": data["timestamp"],
            "user_id": data["user_id"],
            "input": data["input"],
            "output": output_text,
            "latency_ms": latency_ms,
            "status": "SUCCESS"
        }
        
        if any(keyword in output_text.lower() for keyword in ["blocked", "detect", "violate", "policy", "limit"]):
             log_entry["status"] = "BLOCKED"

        self.logs.append(log_entry)
        self.export_json()
        self._monitor(log_entry)
        
        return llm_response

    def log_manual(self, user_id, input_text, output_text, status="BLOCKED"):
        """Manual logging for cases where plugins short-circuit the flow."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "input": input_text,
            "output": output_text,
            "latency_ms": 0,
            "status": status
        }
        self.logs.append(log_entry)
        self.export_json()

    def _monitor(self, entry):
        """
        Monitoring logic to alert on anomalies.
        """
        if entry["status"] == "BLOCKED":
            print(f">>> [MONITORING ALERT] Security block detected for user '{entry['user_id']}'.")
        
        if entry["latency_ms"] > 5000:
            print(f">>> [MONITORING ALERT] High latency detected: {entry['latency_ms']}ms.")

    def export_json(self):
        """Save logs to file."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error exporting audit log: {e}")

    def get_metrics(self):
        """Calculate high-level metrics."""
        total = len(self.logs)
        blocked = sum(1 for log in self.logs if log["status"] == "BLOCKED")
        return {
            "total_requests": total,
            "blocked_requests": blocked,
            "block_rate": (blocked / total) if total > 0 else 0,
            "avg_latency": sum(log["latency_ms"] for log in self.logs) / total if total > 0 else 0
        }
