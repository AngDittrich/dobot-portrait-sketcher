"""Prueba de movimiento mínimo del MG400: avanza 2 mm en X y vuelve.

Sirve para comprobar que el robot obedece de punta a punta (orden, cola de
movimiento y Sync) sin acercarse a nada. No forma parte de la cabina.

Uso:
    python tools/robot_test_move.py [--host 192.168.10.55] [--step 2]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.robot.mg400 import MG400Link  # noqa: E402


def show(label: str, pose: tuple[float, float, float, float]) -> None:
    x, y, z, r = pose
    print(f"  {label:<10} x {x:8.3f}  y {y:8.3f}  z {z:8.3f}  r {r:8.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.10.55")
    parser.add_argument("--step", type=float, default=2.0, help="milímetros a avanzar")
    parser.add_argument("--speed", type=int, default=20, help="porcentaje de velocidad")
    args = parser.parse_args()

    with MG400Link(args.host) as robot:
        mode = robot.mode()
        print(f"robot en modo {mode}", flush=True)
        before = robot.pose()
        show("antes", before)

        robot.speed_factor(args.speed)
        print(f"\nvelocidad al {args.speed} %: avanza {args.step} mm en X", flush=True)
        robot.rel_movl(args.step, 0.0, 0.0, 0.0, speed=args.speed, acc=args.speed)
        time.sleep(0.2)
        moved = robot.pose()
        show("movido", moved)
        print(f"  desplazamiento real en X: {moved[0] - before[0]:+.3f} mm", flush=True)

        print("\nvuelve a su sitio", flush=True)
        robot.rel_movl(-args.step, 0.0, 0.0, 0.0, speed=args.speed, acc=args.speed)
        time.sleep(0.2)
        back = robot.pose()
        show("devuelto", back)
        print(f"  error de vuelta en X: {back[0] - before[0]:+.3f} mm", flush=True)


if __name__ == "__main__":
    main()
