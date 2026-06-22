"""
main.py — Orquestador del pipeline sintético ecommerce-latam-pipeline.

Ejecuta en orden: users → sessions → transactions → invoices → returns → fraud
El catálogo VTEX (discover_categories / extract_products / dedupe_and_build)
es una extracción one-shot y se gestiona por separado via refresh_catalog.py.

Uso:
    python main.py                  # pipeline completo
    python main.py --from sessions  # reanuda desde un paso específico
    python main.py --only fraud     # corre solo un paso
"""

import argparse
import sys
import time
from loguru import logger

# --- importes de cada generador ---
from generators import users, sessions, transactions, invoices, returns, fraud


STEPS = ["users", "sessions", "transactions", "invoices", "returns", "fraud"]

STEP_FN = {
    "users":        users.run,
    "sessions":     sessions.run,
    "transactions": transactions.run,
    "invoices":     invoices.run,
    "returns":      returns.run,
    "fraud":        fraud.run,
}


def run_pipeline(steps: list[str]) -> None:
    total_start = time.perf_counter()
    logger.info(f"Pipeline iniciado — pasos: {steps}")

    for step in steps:
        logger.info(f"▶ {step}")
        step_start = time.perf_counter()
        try:
            STEP_FN[step]()
        except Exception as e:
            logger.error(f"✗ {step} falló: {e}")
            sys.exit(1)
        elapsed = time.perf_counter() - step_start
        logger.success(f"✓ {step} completado en {elapsed:.1f}s")

    total = time.perf_counter() - total_start
    logger.success(f"Pipeline completo en {total:.1f}s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline sintético ecommerce-latam")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--from",
        dest="from_step",
        choices=STEPS,
        metavar="STEP",
        help=f"Reanuda desde STEP inclusive. Opciones: {STEPS}",
    )
    group.add_argument(
        "--only",
        dest="only_step",
        choices=STEPS,
        metavar="STEP",
        help="Ejecuta únicamente STEP.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.only_step:
        steps_to_run = [args.only_step]
    elif args.from_step:
        idx = STEPS.index(args.from_step)
        steps_to_run = STEPS[idx:]
    else:
        steps_to_run = STEPS

    run_pipeline(steps_to_run)