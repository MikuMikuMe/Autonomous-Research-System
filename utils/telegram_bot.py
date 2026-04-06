"""
Telegram Bot — Thin wrapper over the existing FastAPI/WebSocket API.

Receives research ideas as Telegram messages and streams results back.
Delegates all actual work to the LangGraph orchestrator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bot implementation
# ---------------------------------------------------------------------------

class TelegramResearchBot:
    """Telegram bot that forwards research ideas to the orchestrator."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._app: Any = None
        self._running = False

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    def build(self) -> Any:
        """Build the telegram Application. Returns None if deps missing."""
        if not self.is_configured:
            logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled.")
            return None

        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.warning(
                "python-telegram-bot not installed. "
                "Install with: pip install python-telegram-bot"
            )
            return None

        app = ApplicationBuilder().token(self.token).build()

        app.add_handler(CommandHandler("start", self._handle_start))
        app.add_handler(CommandHandler("help", self._handle_help))
        app.add_handler(CommandHandler("status", self._handle_status))
        app.add_handler(CommandHandler("research", self._handle_research))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        self._app = app
        return app

    async def _handle_start(self, update: Any, context: Any) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "🔬 *Autonomous Research System*\n\n"
            "Send me a research idea and I'll investigate it!\n\n"
            "Commands:\n"
            "/research <idea> — Start research on a topic\n"
            "/status — Check if a research task is running\n"
            "/help — Show this message",
            parse_mode="Markdown",
        )

    async def _handle_help(self, update: Any, context: Any) -> None:
        """Handle /help command."""
        await update.message.reply_text(
            "📖 *How to use*\n\n"
            "Simply send me a research idea as a message, or use:\n"
            "`/research Does SMOTE improve fairness in credit scoring?`\n\n"
            "I'll decompose it into claims, search the literature, "
            "verify findings, and send you a report.",
            parse_mode="Markdown",
        )

    async def _handle_status(self, update: Any, context: Any) -> None:
        """Handle /status command."""
        is_running = context.bot_data.get("research_running", False)
        if is_running:
            idea = context.bot_data.get("current_idea", "unknown")
            await update.message.reply_text(f"🔄 Research in progress: _{idea}_", parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ No research task running. Send me an idea!")

    async def _handle_research(self, update: Any, context: Any) -> None:
        """Handle /research <idea> command."""
        if not context.args:
            await update.message.reply_text("Usage: `/research <your research idea>`", parse_mode="Markdown")
            return
        idea = " ".join(context.args)
        await self._run_research(update, context, idea)

    async def _handle_message(self, update: Any, context: Any) -> None:
        """Handle plain text messages as research ideas."""
        idea = update.message.text.strip()
        if len(idea) < 10:
            await update.message.reply_text("Please send a more detailed research idea (at least 10 characters).")
            return
        await self._run_research(update, context, idea)

    async def _run_research(self, update: Any, context: Any, idea: str) -> None:
        """Execute research and stream results to Telegram."""
        if context.bot_data.get("research_running", False):
            await update.message.reply_text("⚠️ A research task is already running. Please wait.")
            return

        context.bot_data["research_running"] = True
        context.bot_data["current_idea"] = idea
        await update.message.reply_text(f"🚀 Starting research on:\n_{idea}_", parse_mode="Markdown")

        try:
            report = await asyncio.to_thread(self._execute_research, idea)

            summary = self._format_report(report)
            # Telegram message limit is 4096 chars
            for chunk in self._chunk_text(summary, 4000):
                await update.message.reply_text(chunk, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Research failed: {e}")
            logger.error("Research failed for '%s': %s", idea, e, exc_info=True)
        finally:
            context.bot_data["research_running"] = False
            context.bot_data.pop("current_idea", None)

    @staticmethod
    def _execute_research(idea: str) -> dict[str, Any]:
        """Run the LangGraph research pipeline synchronously."""
        try:
            from orchestration.langgraph_orchestrator import run_research
            return run_research(idea)
        except Exception as e:
            return {"error": str(e), "research_idea": idea}

    @staticmethod
    def _format_report(report: dict[str, Any]) -> str:
        """Format a research report for Telegram."""
        if "error" in report:
            return f"❌ *Error*: {report['error']}"

        lines = ["📊 *Research Report*\n"]

        domain = report.get("domain", "general")
        lines.append(f"*Domain*: {domain}")

        claims = report.get("claims", [])
        if claims:
            lines.append(f"\n*Claims* ({len(claims)}):")
            for c in claims[:10]:
                text = c.get("text", "") if isinstance(c, dict) else str(c)
                lines.append(f"  • {text[:200]}")

        v_report = report.get("verification_report", {})
        if v_report:
            verified = v_report.get("claims", [])
            n_verified = sum(1 for c in verified if c.get("verified", False))
            lines.append(f"\n*Verified*: {n_verified}/{len(verified)}")

        techniques = report.get("discovered_techniques", [])
        if techniques:
            lines.append(f"\n*Discovered Techniques* ({len(techniques)}):")
            for t in techniques[:5]:
                name = t.get("name", "") if isinstance(t, dict) else str(t)
                lines.append(f"  • {name[:150]}")

        errors = report.get("errors", [])
        if errors:
            lines.append(f"\n⚠️ *Issues* ({len(errors)}):")
            for e in errors[:5]:
                lines.append(f"  • {e[:200]}")

        return "\n".join(lines)

    @staticmethod
    def _chunk_text(text: str, max_len: int = 4000) -> list[str]:
        """Split text into chunks that fit Telegram's message limit."""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            # Find a good split point
            split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks

    def run_polling(self) -> None:
        """Start the bot in polling mode (blocking)."""
        app = self.build()
        if app is None:
            logger.error("Cannot start Telegram bot — not configured.")
            return
        logger.info("Starting Telegram bot in polling mode...")
        app.run_polling()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the Telegram bot from command line."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    bot = TelegramResearchBot()
    if not bot.is_configured:
        print("Error: TELEGRAM_BOT_TOKEN not set.")
        print("Set it in .env or as environment variable.")
        sys.exit(1)
    bot.run_polling()


if __name__ == "__main__":
    main()
