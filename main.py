import argparse
import asyncio
import json
import logging
import sys
from typing import Iterable, Optional

from src.admin_bot import AdminControlBot
from src.bot_agent.agent import BotAgent
from src.common.db import DatabaseManager
from src.common.redis import RedisChannels, RedisManager
from src.config.settings import Settings, get_settings
from src.engine.core.engine_state import EngineState
from src.engine.core.order_book import OrderBook
from src.engine.core.predictive_market_maker import PredictiveMarketMaker
from src.engine.core.trade_matcher import ImmediateArbitrageMatcher
from src.engine.core.trade_tracker import TradeTracker
from src.engine.core.trade_policy import TradePolicy
from src.engine.services.admin_service import AdminCommandService
from src.engine.services.execution_result_service import ExecutionResultProcessor
from src.engine.services.order_book_service import OrderBookManager
from src.engine.services.risk_manager import RiskManager


def _build_redis_manager(settings: Settings) -> RedisManager:
	return RedisManager(
		settings.redis.url,
		RedisChannels(
			group_events=settings.redis.group_events_channel,
			execution_commands=settings.redis.execution_commands_channel,
			execution_results=settings.redis.execution_results_channel,
			admin_commands=settings.redis.admin_commands_channel,
			admin_reports=settings.redis.admin_reports_channel,
		),
	)


async def _launch_agent(agent: BotAgent) -> None:
	await agent.start()
	await agent.run()


async def _monitor_results(redis_manager: RedisManager, channel: str) -> None:
	"""Monitor execution_results channel and print formatted output"""
	logging.info("📊 Monitoring execution results...")
	try:
		async for message in redis_manager.subscribe(channel):
			try:
				result = json.loads(message)
				status_emoji = "✅" if result.get("status") == "success" else "❌"
				print(f"\n{status_emoji} EXECUTION RESULT:")
				print(f"   Agent: {result.get('alias', 'N/A')}")
				print(f"   Status: {result.get('status', 'N/A')}")
				print(f"   Trade ID: {result.get('trade_id', 'N/A')}")
				if result.get("details"):
					print(f"   Details: {json.dumps(result['details'], ensure_ascii=False)}")
				print("-" * 60)
			except json.JSONDecodeError:
				logging.warning("Failed to decode result: %s", message)
	except asyncio.CancelledError:
		logging.info("Result monitoring stopped")


async def _run_agents(settings: Settings) -> None:
	logging.info("🚀 Starting Telegram Arbitrage Bot System")
	logging.info("=" * 60)
	
	# Initialize database
	DatabaseManager(settings.database.path).initialize_schema()
	logging.info("✓ Database initialized")

	# Setup Redis
	redis_manager = _build_redis_manager(settings)
	logging.info("✓ Redis connection ready")

	# Create agents
	agents: Iterable[BotAgent] = (
		BotAgent("source", settings.source_bot, settings.telegram, redis_manager),
		BotAgent("destination", settings.destination_bot, settings.telegram, redis_manager),
	)
	logging.info("✓ Bot agents created")
	logging.info("=" * 60)
	logging.info("🔍 Monitoring groups - send messages to test:")
	logging.info("   📨 Source group: %s", settings.source_bot.alias)
	logging.info("   📨 Destination group: %s", settings.destination_bot.alias)
	logging.info("=" * 60)

	# Start result monitoring in background
	monitor_task = asyncio.create_task(
		_monitor_results(redis_manager, redis_manager.channels.execution_results)
	)

	try:
		await asyncio.gather(*(_launch_agent(agent) for agent in agents))
	finally:
		monitor_task.cancel()
		try:
			await monitor_task
		except asyncio.CancelledError:
			pass


async def _run_engine(settings: Settings) -> None:
	logging.info("⚙️ Starting arbitrage engine order book service")
	database = DatabaseManager(settings.database.path)
	database.initialize_schema()

	redis_manager = _build_redis_manager(settings)
	order_book = OrderBook()
	trade_tracker = TradeTracker()
	engine_state = EngineState()
	risk_manager = RiskManager(
		redis_manager=redis_manager,
		order_book=order_book,
		engine_state=engine_state,
		execution_commands_channel=redis_manager.channels.execution_commands,
		admin_reports_channel=redis_manager.channels.admin_reports,
		break_even_timeout_seconds=settings.engine.exit_break_even_timeout_seconds,
		stop_loss_timeout_seconds=settings.engine.exit_stop_loss_timeout_seconds,
		stop_loss_price_offset=settings.engine.stop_loss_price_offset,
		circuit_breaker_seconds=settings.engine.circuit_breaker_pause_seconds,
		source_alias=settings.source_bot.alias,
		destination_alias=settings.destination_bot.alias,
	)
	policy = TradePolicy(
		fixed_spread_delta=settings.engine.fixed_spread_delta,
		base_carry_limit=settings.engine.base_carry_limit,
		opportunity_carry_limit=settings.engine.opportunity_carry_limit,
	)
	matcher = ImmediateArbitrageMatcher(
		order_book=order_book,
		redis_manager=redis_manager,
		execution_commands_channel=redis_manager.channels.execution_commands,
		policy=policy,
		trade_tracker=trade_tracker,
		engine_state=engine_state,
	)
	predictive = PredictiveMarketMaker(
		order_book=order_book,
		redis_manager=redis_manager,
		trade_tracker=trade_tracker,
		engine_state=engine_state,
		execution_commands_channel=redis_manager.channels.execution_commands,
		predictive_price_delta=settings.engine.predictive_price_delta,
		predictive_suffix_digits=settings.engine.predictive_suffix_digits,
		speculative_timeout_seconds=settings.engine.speculative_trade_timeout_seconds,
		destination_alias=settings.destination_bot.alias,
		policy=policy,
		source_expiry_seconds=settings.engine.source_order_expiry_seconds,
	)
	manager = OrderBookManager(
		redis_manager=redis_manager,
		order_book=order_book,
		group_events_channel=redis_manager.channels.group_events,
		reconciliation_interval_seconds=settings.engine.reconciliation_interval_seconds,
		stale_order_seconds=settings.engine.stale_order_seconds,
		executed_trades_cache_key=settings.engine.executed_trades_cache_key,
		event_listeners=[matcher.process_event, predictive.process_event],
	)
	results_processor = ExecutionResultProcessor(
		redis_manager=redis_manager,
		channel=redis_manager.channels.execution_results,
		tracker=trade_tracker,
		database=database,
		executed_cache_key=settings.engine.executed_trades_cache_key,
		executed_cache_ttl=settings.engine.executed_trades_cache_ttl_seconds,
		listeners=[predictive.handle_execution_result, risk_manager.handle_execution_result],
		trade_observer=risk_manager.handle_trade_final,
	)
	admin_service = AdminCommandService(
		redis_manager=redis_manager,
		command_channel=redis_manager.channels.admin_commands,
		report_channel=redis_manager.channels.admin_reports,
		order_book=order_book,
		engine_state=engine_state,
		matcher=matcher,
		predictive=predictive,
		risk_manager=risk_manager,
		policy=policy,
		database=database,
	)
	admin_service.register_shutdown_callback(manager.stop)
	admin_service.register_shutdown_callback(results_processor.stop)
	admin_bot_controller = None
	if settings.admin_bot.enabled and settings.admin_bot.bot_token and settings.admin_bot.chat_id is not None:
		admin_bot_controller = AdminControlBot(
			redis_manager=redis_manager,
			api_id=settings.telegram.api_id,
			api_hash=settings.telegram.api_hash,
			bot_token=settings.admin_bot.bot_token,
			chat_id=settings.admin_bot.chat_id,
			policy_snapshot=policy.snapshot,
			initial_auto_delay=settings.source_bot.cancel_ack_delay_seconds,
			status_refresh_seconds=settings.admin_bot.status_refresh_seconds,
			source_alias=settings.source_bot.alias,
			destination_alias=settings.destination_bot.alias,
			engine_config={
				"predictive_price_delta": settings.engine.predictive_price_delta,
				"predictive_suffix_digits": settings.engine.predictive_suffix_digits,
				"speculative_trade_timeout_seconds": settings.engine.speculative_trade_timeout_seconds,
				"source_order_expiry_seconds": settings.engine.source_order_expiry_seconds,
				"exit_break_even_timeout_seconds": settings.engine.exit_break_even_timeout_seconds,
				"exit_stop_loss_timeout_seconds": settings.engine.exit_stop_loss_timeout_seconds,
				"stop_loss_price_offset": settings.engine.stop_loss_price_offset,
				"circuit_breaker_pause_seconds": settings.engine.circuit_breaker_pause_seconds,
			},
			initial_monitor_only=engine_state.monitor_only,
		)
		admin_service.register_shutdown_callback(admin_bot_controller.stop)

	tasks = [
		manager.run(),
		results_processor.run(),
		admin_service.run(),
	]
	if admin_bot_controller is not None:
		tasks.append(admin_bot_controller.run())

	try:
		await asyncio.gather(*tasks)
	except asyncio.CancelledError:
		manager.stop()
		results_processor.stop()
		admin_service.stop()
		if admin_bot_controller is not None:
			await admin_bot_controller.stop()
		raise
	except Exception:
		manager.stop()
		results_processor.stop()
		admin_service.stop()
		if admin_bot_controller is not None:
			await admin_bot_controller.stop()
		raise


async def _publish_command(settings: Settings, json_payload: str, channel_alias: str) -> None:
	payload = json.loads(json_payload)
	redis_manager = _build_redis_manager(settings)
	channels = settings.redis
	channel_map = {
		"group_events": channels.group_events_channel,
		"execution_commands": channels.execution_commands_channel,
		"execution_results": channels.execution_results_channel,
		"admin_commands": channels.admin_commands_channel,
		"admin_reports": channels.admin_reports_channel,
	}
	channel = channel_map.get(channel_alias, channel_alias)

	await redis_manager.publish_json(channel, payload)
	logging.info("Published payload to %s: %s", channel_alias, payload)


async def _listen_channel(settings: Settings, channel_alias: str) -> None:
	redis_manager = _build_redis_manager(settings)
	channels = settings.redis
	channel_map = {
		"group_events": channels.group_events_channel,
		"execution_commands": channels.execution_commands_channel,
		"execution_results": channels.execution_results_channel,
		"admin_commands": channels.admin_commands_channel,
		"admin_reports": channels.admin_reports_channel,
	}
	channel = channel_map.get(channel_alias, channel_alias)

	logging.info("Listening on channel %s (%s) — press Ctrl+C to stop", channel_alias, channel)
	try:
		async for message in redis_manager.subscribe(channel):
			try:
				parsed = json.loads(message)
				print(json.dumps(parsed, ensure_ascii=False, indent=2))
			except json.JSONDecodeError:
				print(message)
	except KeyboardInterrupt:
		logging.info("Stopped listening to %s", channel_alias)


def _configure_logging(level: str) -> None:
	logging.basicConfig(
		level=level,
		format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
	)


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Telegram Arbitrage Bot controller")
	subparsers = parser.add_subparsers(dest="command")
	parser.set_defaults(command="run")

	subparsers.add_parser("run", help="Start both Telegram agents (default)")
	subparsers.add_parser("engine", help="Run the arbitrage engine order book service")

	publish_parser = subparsers.add_parser(
		"publish", help="Publish a raw JSON payload to a Redis channel (default: execution_commands)"
	)
	publish_parser.add_argument("json", help="JSON payload to publish")
	publish_parser.add_argument(
		"--channel",
		default="execution_commands",
		help="Channel alias or exact name to publish to (default: execution_commands)",
	)

	listen_parser = subparsers.add_parser(
		"listen", help="Listen to a Redis channel and stream messages to stdout"
	)
	listen_parser.add_argument(
		"--channel",
		default="group_events",
		help="Channel alias or exact name to subscribe to (default: group_events)",
	)

	return parser.parse_args()


async def _async_entrypoint(args: argparse.Namespace) -> None:
	settings = get_settings()
	_configure_logging(settings.log_level)

	if args.command == "run":
		await _run_agents(settings)
	elif args.command == "engine":
		await _run_engine(settings)
	elif args.command == "publish":
		await _publish_command(settings, args.json, args.channel)
	elif args.command == "listen":
		await _listen_channel(settings, args.channel)
	else:  # pragma: no cover
		raise ValueError(f"Unknown command: {args.command}")


def main() -> None:
	args = _parse_args()
	try:
		asyncio.run(_async_entrypoint(args))
	except KeyboardInterrupt:
		print("Interrupted by user", file=sys.stderr)


if __name__ == "__main__":
	main()
