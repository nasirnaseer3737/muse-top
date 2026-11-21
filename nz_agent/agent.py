"""The agent loop for NZ Agent.

One turn:
1. Build a prompt from the user's message, remembered facts, tool list
   and recent history.
2. Ask the LLM. The LLM may answer directly, or emit ``CALL <name> <json>``
   lines to use tools.
3. Execute each requested tool, feed the results back to the LLM once,
   and return the final answer.
"""
from __future__ import annotations

from .config import Config
from .llm import GeminiClient
from .memory import Memory
from .tools import ToolRegistry, build_default_registry, parse_tool_call

SYSTEM_PROMPT = """You are NZ Agent, a helpful personal assistant.

You have these tools (call one per line, exactly like this):
CALL <tool_name> {{"arg": "value"}}

Tools:
{tools}

Facts you remember:
{facts}

Rules:
- If the user asks for the time or a fact, use the matching tool.
- If you call a tool, wait for its result before answering.
- Never invent a tool name. Never reveal API keys.
- Keep answers short and in the user's language.
"""


class Agent:
    def __init__(
        self,
        config: Config | None = None,
        llm: GeminiClient | None = None,
        memory: Memory | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.config = config or Config.from_env()
        self.memory = memory or Memory(self.config.memory_path)
        self.registry = registry or build_default_registry(self.memory)
        self.llm = llm or GeminiClient(
            api_key=self.config.api_key,
            model=self.config.model,
            timeout_seconds=self.config.llm_timeout_seconds,
        )
        self.history: list[tuple[str, str]] = []  # (role, text), oldest first

    def _build_prompt(self, user_message: str) -> str:
        history_text = ""
        for role, text in self.history[-self.config.max_history_turns :]:
            history_text += f"{role}: {text}\n"
        prompt = SYSTEM_PROMPT.format(
            tools=self.registry.describe(),
            facts=self.memory.render_for_prompt(),
        )
        if history_text:
            prompt += f"\nRecent conversation:\n{history_text}"
        prompt += f"\nUser: {user_message}\nAssistant:"
        return prompt

    def _run_tool_calls(self, reply: str) -> list[str]:
        """Execute every CALL line in the LLM reply; return their results."""
        results = []
        for line in reply.splitlines():
            parsed = parse_tool_call(line)
            if parsed is None:
                continue
            name, args = parsed
            results.append(f"Tool {name} result: {self.registry.call(name, args)}")
        return results

    def chat(self, user_message: str) -> str:
        message = user_message.strip()
        if not message:
            return "Please type a message."
        prompt = self._build_prompt(message)
        reply = self.llm.generate(prompt)

        tool_results = self._run_tool_calls(reply)
        if tool_results:
            follow_up = (
                prompt
                + f"\n{reply}\n\nTool results:\n"
                + "\n".join(tool_results)
                + "\nNow give the user your final short answer."
            )
            final = self.llm.generate(follow_up)
            # A mock LLM echoes the prompt; strip the tool-result block back out.
            reply = final if final.strip() else reply

        self.history.append(("User", message))
        self.history.append(("Assistant", reply))
        self.history = self.history[-self.config.max_history_turns * 2 :]
        return reply
