"""
Receptor TCP de demostración — Taller de Potencia
=================================================
Servidor TCP que recibe los datos enviados por la app de medición del DL3000
y los muestra/guarda. Pensado para que el grupo SCADA pueda verificar el
flujo Ethernet antes de integrarlo a su HMI.

Protocolo recibido (una línea por medida, ASCII):
    t,v,i\\n
    donde t [s], v [V], i [A]

Uso:
    python receptor_ethernet_demo.py                  # 0.0.0.0:5025 con gráfica
    python receptor_ethernet_demo.py --port 6000      # cambia puerto
    python receptor_ethernet_demo.py --no-plot        # solo consola + CSV
    python receptor_ethernet_demo.py --csv salida.csv # nombre de CSV propio

Dependencias:
    pip install matplotlib       (solo si quieres la gráfica en vivo)
"""

from __future__ import annotations

import argparse
import csv
import os
import socket
import threading
import time
from datetime import datetime


# ── Búfer compartido entre el hilo del servidor y el hilo de la gráfica ──────
class DataBuffer:
    """Almacena las muestras recibidas. Thread-safe."""

    def __init__(self, max_points: int = 5000):
        self.t: list[float] = []
        self.v: list[float] = []
        self.i: list[float] = []
        self.max_points = max_points
        self._lock = threading.Lock()
        self.client_addr: str | None = None
        self.last_update: float = 0.0
        self.total_received: int = 0

    def append(self, t: float, v: float, i: float):
        with self._lock:
            self.t.append(t)
            self.v.append(v)
            self.i.append(i)
            self.total_received += 1
            self.last_update = time.time()
            if len(self.t) > self.max_points:
                # mantener solo los últimos max_points
                cut = len(self.t) - self.max_points
                self.t = self.t[cut:]
                self.v = self.v[cut:]
                self.i = self.i[cut:]

    def snapshot(self):
        with self._lock:
            return list(self.t), list(self.v), list(self.i)


# ── Hilo del servidor TCP ────────────────────────────────────────────────────
def run_server(host: str, port: int, buf: DataBuffer, csv_writer, csv_file):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(5)
    print(f"[server] Escuchando en {host}:{port} (Ctrl-C para salir)")

    while True:
        try:
            conn, addr = srv.accept()
        except OSError:
            break
        ip_port = f"{addr[0]}:{addr[1]}"
        buf.client_addr = ip_port
        print(f"[server] Cliente conectado: {ip_port}")

        with conn:
            handle_client(conn, ip_port, buf, csv_writer, csv_file)

        print(f"[server] Cliente {ip_port} desconectado")


def handle_client(conn, ip_port, buf, csv_writer, csv_file):
    """Lee líneas del socket y las parsea como `t,v,i\\n`."""
    leftover = b""
    while True:
        try:
            chunk = conn.recv(4096)
        except ConnectionResetError:
            break
        if not chunk:
            break

        data = leftover + chunk
        lines = data.split(b"\n")
        leftover = lines.pop()  # último fragmento puede estar incompleto

        for line in lines:
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                parts = line.split(",")
                if len(parts) != 3:
                    raise ValueError("se esperaban 3 campos")
                t = float(parts[0])
                v = float(parts[1])
                i = float(parts[2])
            except ValueError as e:
                print(f"[parse error] {e!s} en línea: {line!r}")
                continue

            buf.append(t, v, i)
            p = v * i  # potencia activa instantánea (aprox)
            print(f"  rx [{ip_port}]  t={t:8.3f}s  V={v:9.4f} V  "
                  f"I={i:9.5f} A  P={p:9.3f} W")

            if csv_writer is not None:
                csv_writer.writerow(
                    [datetime.now().isoformat(timespec="milliseconds"),
                     ip_port, f"{t:.4f}", f"{v:.6f}", f"{i:.6f}", f"{p:.4f}"]
                )
                csv_file.flush()


# ── Gráfica en vivo (opcional, en hilo principal) ────────────────────────────
def run_plot(buf: DataBuffer, port: int):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    fig, (ax_v, ax_i) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.canvas.manager.set_window_title(f"Receptor SCADA — puerto {port}")
    fig.patch.set_facecolor("#f9f9f9")
    line_v, = ax_v.plot([], [], color="#5B8C5A", lw=1.5, label="V medido")
    line_i, = ax_i.plot([], [], color="#E8523A", lw=1.5, label="I medida")

    for ax, lbl in [(ax_v, "Voltaje (V)"), (ax_i, "Corriente (A)")]:
        ax.set_ylabel(lbl)
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.legend(loc="upper right")
    ax_i.set_xlabel("t del perfil [s]")
    fig.suptitle("Esperando datos…", fontsize=10)
    fig.tight_layout()

    def update(_):
        t, v, i = buf.snapshot()
        if not t:
            return line_v, line_i
        line_v.set_data(t, v)
        line_i.set_data(t, i)
        for ax, ys in [(ax_v, v), (ax_i, i)]:
            ax.set_xlim(min(t), max(t) + 0.01)
            if ys:
                lo, hi = min(ys), max(ys)
                pad = max((hi - lo) * 0.1, 1e-3)
                ax.set_ylim(lo - pad, hi + pad)

        cli = buf.client_addr or "—"
        fig.suptitle(
            f"Cliente: {cli}   |   Paquetes recibidos: {buf.total_received}",
            fontsize=10,
        )
        return line_v, line_i

    _ = FuncAnimation(fig, update, interval=500, blit=False, cache_frame_data=False)
    plt.show()


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0",
                    help="IP local de escucha (default: 0.0.0.0, todas las interfaces)")
    ap.add_argument("--port", type=int, default=5025,
                    help="Puerto TCP de escucha (default: 5025)")
    ap.add_argument("--no-plot", action="store_true",
                    help="No mostrar gráfica en vivo (solo consola + CSV)")
    ap.add_argument("--csv", default=None,
                    help="Archivo CSV de salida (default: rx_<timestamp>.csv)")
    args = ap.parse_args()

    csv_path = args.csv or f"rx_{datetime.now():%Y%m%d_%H%M%S}.csv"
    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["wallclock", "client", "t_perfil_s",
                         "V_volts", "I_amps", "P_watts"])
    print(f"[server] Guardando CSV en: {os.path.abspath(csv_path)}")

    buf = DataBuffer()

    th = threading.Thread(
        target=run_server,
        args=(args.host, args.port, buf, csv_writer, csv_file),
        daemon=True,
    )
    th.start()

    try:
        if args.no_plot:
            print("[server] Modo solo-consola. Ctrl-C para salir.")
            while True:
                time.sleep(1)
        else:
            try:
                run_plot(buf, args.port)
            except ImportError:
                print("[server] matplotlib no instalado. "
                      "Corre con --no-plot o haz: pip install matplotlib")
                while True:
                    time.sleep(1)
    except KeyboardInterrupt:
        print("\n[server] Saliendo…")
    finally:
        csv_file.close()


if __name__ == "__main__":
    main()
