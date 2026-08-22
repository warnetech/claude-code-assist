"""
Warnetech CLI Main Module
Command-line interface for warnetech data protection and AI firewall.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from warnetech_cli.config import Config
from warnetech_cli.commands import Commands
from warnetech_cli.logging import setup_logging, log_operation


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for warnetech CLI."""
    parser = argparse.ArgumentParser(
        description="Warnetech CLI - Data Protection & AI Firewall",
        epilog="For more information, visit https://warnetech.ai",
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: ~/.warnetech/config.json)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="json",
        choices=["json", "text", "compact"],
        help="Output format",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version="warnetech-cli 1.0.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("status", help="Get system status")

    metrics_parser = subparsers.add_parser("metrics", help="Retrieve system metrics")
    metrics_parser.add_argument("--source-id", default="cli", help="Source ID to query metrics for")

    signatures_parser = subparsers.add_parser("signatures", help="List attack signatures")
    signatures_parser.add_argument("--attack-type", default=None, help="Filter by attack type")

    learn_parser = subparsers.add_parser("learn", help="Report an outcome to the adaptive learning model")
    learn_parser.add_argument("attack_type", help="Attack type, e.g. sql_injection")
    learn_parser.add_argument("pattern", help="The pattern that matched (or should have matched)")
    learn_parser.add_argument("--false-positive", action="store_true", help="Report this as a false positive instead of a true positive")

    recover_parser = subparsers.add_parser("recover", help="Recover from attack")
    recover_parser.add_argument("attack_id", help="Attack ID to recover")

    slice_parser = subparsers.add_parser("slice", help="Create data slices")
    slice_parser.add_argument("data_path", help="Path to data file")
    slice_parser.add_argument(
        "--window", default="1hour", help="Slice window size"
    )

    compress_parser = subparsers.add_parser("compress", help="Compress data")
    compress_parser.add_argument("data_path", help="Path to data file")
    compress_parser.add_argument(
        "--method",
        default="zstd-medium",
        choices=["lz4", "zstd-fast", "zstd-medium", "zstd-max"],
        help="Compression method",
    )

    ghost_create_parser = subparsers.add_parser(
        "ghost-create", help="Create ghost copy"
    )
    ghost_create_parser.add_argument("data_path", help="Path to data file")
    ghost_create_parser.add_argument(
        "--source-id", default="auto", help="Source ID"
    )

    ghost_recall_parser = subparsers.add_parser(
        "ghost-recall", help="Recall ghost copy"
    )
    ghost_recall_parser.add_argument("ghost_id", help="Ghost ID to recall")

    retention_apply_parser = subparsers.add_parser(
        "retention-apply", help="Apply retention policy"
    )
    retention_apply_parser.add_argument(
        "policy_name",
        choices=["hot", "warm", "ghost"],
        help="Policy to apply",
    )

    retention_policy_parser = subparsers.add_parser(
        "retention-policy", help="Manage retention policies"
    )
    retention_policy_parser.add_argument(
        "action",
        choices=["list", "get"],
        help="Policy action",
    )
    retention_policy_parser.add_argument(
        "--policy", default="hot", help="Policy name"
    )

    ai_query_parser = subparsers.add_parser("ai-query", help="Query AI system")
    ai_query_parser.add_argument("query", help="Query text")

    ai_recall_parser = subparsers.add_parser(
        "ai-recall", help="Recall data using AI"
    )
    ai_recall_parser.add_argument("dataset_id", help="Dataset ID")

    export_parser = subparsers.add_parser("export", help="Export data")
    export_parser.add_argument("data_path", help="Path to data file")
    export_parser.add_argument(
        "--format",
        default="json",
        choices=["json", "parquet", "csv"],
        help="Export format",
    )

    import_parser = subparsers.add_parser("import", help="Import data")
    import_parser.add_argument("data_path", help="Path to data file")
    import_parser.add_argument(
        "--format",
        default="json",
        choices=["json", "parquet", "csv"],
        help="Import format",
    )

    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_parser.add_argument(
        "action",
        choices=["show", "get"],
        help="Config action",
    )
    config_parser.add_argument("--key", help="Config key to get")

    subparsers.add_parser("server-ping", help="Ping server")
    subparsers.add_parser("db-check", help="Check database connectivity")
    subparsers.add_parser("db-sync", help="Sync with database")
    subparsers.add_parser("ai-diagnose", help="Run the full system self-test")

    return parser


def format_output(
    result: dict, output_format: str = "json"
) -> str:
    """Format command output."""
    if output_format == "json":
        return json.dumps(result, indent=2, default=str)
    elif output_format == "compact":
        return json.dumps(result, default=str)
    else:
        lines = []
        for key, value in result.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{key}:")
                lines.append(json.dumps(value, indent=2, default=str))
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    config_path = Path(args.config) if args.config else None
    config = Config(config_path)
    config.set("log_level", args.log_level)

    logger = setup_logging(log_level=args.log_level)
    commands = Commands(config)

    result = None

    try:
        if args.command == "status":
            result = commands.status()
        elif args.command == "metrics":
            result = commands.metrics(args.source_id)
        elif args.command == "signatures":
            result = commands.signatures(args.attack_type)
        elif args.command == "learn":
            result = commands.learn(args.attack_type, args.pattern, not args.false_positive)
        elif args.command == "recover":
            result = commands.recover(args.attack_id)
        elif args.command == "slice":
            result = commands.slice(args.data_path, args.window)
        elif args.command == "compress":
            result = commands.compress(args.data_path, args.method)
        elif args.command == "ghost-create":
            result = commands.ghost_create(args.data_path, args.source_id)
        elif args.command == "ghost-recall":
            result = commands.ghost_recall(args.ghost_id)
        elif args.command == "retention-apply":
            result = commands.retention_apply(args.policy_name)
        elif args.command == "retention-policy":
            result = commands.retention_policy(args.action, args.policy)
        elif args.command == "ai-query":
            result = commands.ai_query(args.query)
        elif args.command == "ai-recall":
            result = commands.ai_recall(args.dataset_id)
        elif args.command == "export":
            result = commands.export(args.data_path, args.format)
        elif args.command == "import":
            result = commands.import_data(args.data_path, args.format)
        elif args.command == "config":
            result = commands.config(args.action, args.key)
        elif args.command == "server-ping":
            result = commands.server_ping()
        elif args.command == "db-check":
            result = commands.db_check()
        elif args.command == "db-sync":
            result = commands.db_sync()
        elif args.command == "ai-diagnose":
            result = commands.ai_diagnose()
        else:
            logger.error(f"Unknown command: {args.command}")
            return 1

        if result:
            log_operation(
                logger,
                args.command,
                "success",
                0,
            )
            output = format_output(result, args.output)
            print(output)
            return 0
        else:
            log_operation(
                logger,
                args.command,
                "failure",
                0,
            )
            return 1

    except Exception as e:
        logger.error(f"Error executing {args.command}: {str(e)}")
        log_operation(
            logger,
            args.command,
            "error",
            0,
            error=str(e),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
