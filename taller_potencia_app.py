"""
Taller de Potencia — Interfaz de Control
Universidad de los Andes | IELE — Semestre VIII
"""
import os
import glob
import csv
import time
import socket
import threading
from datetime import datetime

import numpy as np
import pandas as pd

import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

try:
    import pyvisa
    PYVISA_OK = True
except ImportError:
    PYVISA_OK = False

# ── Rutas base ─────────────────────────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
PERFILES_DIR      = os.path.join(BASE_DIR, "Perfiles de carga", "barrido_fp_resultados")
RESULTADOS_HIL_DIR = os.path.join(BASE_DIR, "Perfiles de carga", "Resultados_Perfiles_Carga")
DATOS_DIR         = os.path.join(BASE_DIR, "Datos de prueba")
RESOURCE_ID       = "USB0::0x1AB1::0x0E11::DL3A243500940::INSTR"

os.makedirs(DATOS_DIR, exist_ok=True)

# ── Paleta de colores ──────────────────────────────────────────────────────────
C_RES  = "#E8523A"
C_IND  = "#2E86AB"
C_Q    = "#6C63AC"
C_V    = "#5B8C5A"
C_I    = "#E8523A"

PLOT_MAX_PTS = 10_000   # máximo de puntos a graficar para HIL (downsample)


# ══════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Taller de Potencia — IELE · Universidad de los Andes")
        self.geometry("1300x820")
        self.minsize(950, 650)

        # ── variables de estado ────────────────────────────────────────────
        self.fp_var       = tk.StringVar(value="0.85")
        self.tipo_var     = tk.StringVar(value="residencial")
        self.usb_var      = tk.StringVar(value=RESOURCE_ID)
        self.eth_host_var = tk.StringVar(value="192.168.1.100")
        self.eth_port_var = tk.IntVar(value=5025)
        self.imax_var     = tk.DoubleVar(value=1.0)
        self.speed_var    = tk.DoubleVar(value=1.0)
        self.loop_var     = tk.BooleanVar(value=False)
        self.eth_live_var = tk.BooleanVar(value=False)
        self.status_var   = tk.StringVar(value="Listo.")
        self.hil_path_var = tk.StringVar()

        self.perfil_df  = None
        self.hil_df     = None
        self.inst       = None       # pyvisa resource
        self.eth_sock   = None      # socket Ethernet (live)
        self._running   = False
        self._hw_data   = {"t": [], "v": [], "i": []}

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════
    # CONSTRUCCIÓN DE UI
    # ══════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self._build_topbar()
        self._build_notebook()
        self._build_statusbar()

    # ── Barra superior ─────────────────────────────────────────────────────
    def _build_topbar(self):
        bar = ttk.Frame(self, padding=(8, 5))
        bar.pack(fill="x", side="top")

        # Selector FP
        ttk.Label(bar, text="Factor de Potencia:").pack(side="left")
        fps = self._list_fp_values()
        self.fp_combo = ttk.Combobox(bar, textvariable=self.fp_var,
                                     values=fps, width=7, state="readonly")
        self.fp_combo.pack(side="left", padx=(3, 14))

        # Tipo de carga
        ttk.Label(bar, text="Tipo:").pack(side="left")
        ttk.Radiobutton(bar, text="Residencial",
                         variable=self.tipo_var, value="residencial").pack(side="left")
        ttk.Radiobutton(bar, text="Industrial",
                         variable=self.tipo_var, value="industrial").pack(side="left", padx=(0, 14))

        ttk.Button(bar, text="Cargar datos", command=self.cargar_datos).pack(side="left", padx=3)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        # Control hardware
        ttk.Button(bar, text="Conectar USB", command=self.conectar_usb).pack(side="left", padx=3)

        self.btn_run = ttk.Button(bar, text="▶  Enviar a DL3000",
                                  command=self.iniciar_envio, state="disabled")
        self.btn_run.pack(side="left", padx=3)

        self.btn_stop = ttk.Button(bar, text="■  Detener",
                                   command=self.detener, state="disabled")
        self.btn_stop.pack(side="left", padx=3)

        ttk.Checkbutton(bar, text="Continuo", variable=self.loop_var).pack(side="left", padx=5)

        ttk.Label(bar, text="Velocidad ×").pack(side="left", padx=(8, 2))
        ttk.Spinbox(bar, from_=0.1, to=1000, increment=1.0,
                    textvariable=self.speed_var, width=6).pack(side="left")

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Checkbutton(bar, text="Ethernet en vivo",
                         variable=self.eth_live_var).pack(side="left", padx=3)
        ttk.Button(bar, text="Enviar Ethernet (post)",
                   command=self.enviar_ethernet_post).pack(side="left", padx=3)

    # ── Notebook ────────────────────────────────────────────────────────────
    def _build_notebook(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)

        t1 = ttk.Frame(self.nb)
        self.nb.add(t1, text="   Perfil de Carga (P, Q)   ")
        self._build_tab_perfil(t1)

        t2 = ttk.Frame(self.nb)
        self.nb.add(t2, text="   Dinámica HIL   ")
        self._build_tab_hil(t2)

        t3 = ttk.Frame(self.nb)
        self.nb.add(t3, text="   Control Hardware   ")
        self._build_tab_hw(t3)

    # ── Tab 1 — Perfil de carga ─────────────────────────────────────────────
    def _build_tab_perfil(self, parent):
        fig, (ax_p, ax_q) = plt.subplots(2, 1, figsize=(11, 5), sharex=True,
                                          gridspec_kw={"hspace": 0.35})
        fig.patch.set_facecolor("#f9f9f9")
        self.fig_perf = fig
        self.ax_perf_p = ax_p
        self.ax_perf_q = ax_q

        for ax, lbl in zip([ax_p, ax_q], ["P [pu]", "Q [pu]"]):
            ax.set_ylabel(lbl, fontsize=8)
            ax.set_xlabel("Tiempo [s]", fontsize=8)
            ax.grid(True, linestyle=":", alpha=0.4)
            ax.tick_params(labelsize=7)
        ax_p.set_title("Carga no seleccionada", fontsize=9, fontweight="bold")
        ax_q.set_title("Potencia Reactiva", fontsize=9, fontweight="bold")

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(canvas, parent).update()
        self.canvas_perf = canvas

    # ── Tab 2 — Dinámica HIL ────────────────────────────────────────────────
    def _build_tab_hil(self, parent):
        # Barra de selección de archivo HIL
        ctrl = ttk.Frame(parent, padding=5)
        ctrl.pack(fill="x")
        ttk.Label(ctrl, text="Archivo HIL:").pack(side="left")
        self.hil_combo = ttk.Combobox(ctrl, textvariable=self.hil_path_var, width=72)
        self.hil_combo.pack(side="left", padx=4)
        ttk.Button(ctrl, text="Cargar HIL", command=self.cargar_hil).pack(side="left")

        # 4 subgráficas (una por variable)
        fig, axes = plt.subplots(2, 2, figsize=(11, 5))
        fig.patch.set_facecolor("#f9f9f9")
        self.fig_hil = fig
        self.axes_hil = axes
        fig.suptitle("Selecciona un archivo HIL y presiona Cargar HIL",
                     fontsize=9, color="gray")

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(canvas, parent).update()
        self.canvas_hil = canvas

    # ── Tab 3 — Control hardware ────────────────────────────────────────────
    def _build_tab_hw(self, parent):
        # Panel de configuración
        cfg = ttk.LabelFrame(parent, text="Parámetros de conexión", padding=6)
        cfg.pack(fill="x", padx=10, pady=6)

        ttk.Label(cfg, text="USB Resource ID:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(cfg, textvariable=self.usb_var, width=56).grid(
            row=0, column=1, columnspan=4, sticky="w", padx=4)

        ttk.Label(cfg, text="Ethernet IP:").grid(
            row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(cfg, textvariable=self.eth_host_var, width=18).grid(
            row=1, column=1, sticky="w", padx=4)
        ttk.Label(cfg, text="Puerto:").grid(row=1, column=2, sticky="w", padx=(10, 2))
        ttk.Entry(cfg, textvariable=self.eth_port_var, width=8).grid(
            row=1, column=3, sticky="w")

        ttk.Label(cfg, text="I_max enviado (A):").grid(
            row=2, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(cfg, textvariable=self.imax_var, width=8).grid(
            row=2, column=1, sticky="w", padx=4)
        ttk.Label(cfg, text="← corriente máxima escalada al DL3000", foreground="gray").grid(
            row=2, column=2, columnspan=3, sticky="w")

        # Gráfica en vivo
        fig, (ax_v, ax_i) = plt.subplots(2, 1, figsize=(11, 4.5), sharex=True,
                                          gridspec_kw={"hspace": 0.4})
        fig.patch.set_facecolor("#f9f9f9")
        self.fig_hw   = fig
        self.ax_hw_v  = ax_v
        self.ax_hw_i  = ax_i

        for ax, lbl in zip([ax_v, ax_i], ["Voltaje (V)", "Corriente (A)"]):
            ax.set_ylabel(lbl, fontsize=8)
            ax.set_xlabel("Tiempo [s]", fontsize=8)
            ax.grid(True, linestyle=":", alpha=0.4)
            ax.tick_params(labelsize=7)
        ax_v.set_title("Voltaje medido — DL3000", fontsize=9, fontweight="bold")
        ax_i.set_title("Corriente medida — DL3000", fontsize=9, fontweight="bold")

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8)
        NavigationToolbar2Tk(canvas, parent).update()
        self.canvas_hw = canvas

    # ── Barra de estado ─────────────────────────────────────────────────────
    def _build_statusbar(self):
        ttk.Label(self, textvariable=self.status_var,
                  relief="sunken", anchor="w", padding=(6, 2)).pack(
            fill="x", side="bottom")

    # ══════════════════════════════════════════════════════════════════════
    # LÓGICA — PERFIL DE CARGA
    # ══════════════════════════════════════════════════════════════════════

    def _list_fp_values(self):
        folders = sorted(glob.glob(os.path.join(PERFILES_DIR, "FP_*")))
        result  = []
        for f in folders:
            name = os.path.basename(f)
            if name.startswith("FP_") and os.path.isdir(f):
                result.append(name[3:])
        return result or ["0.85"]

    @staticmethod
    def _fp_resultados_keys(fp):
        """
        Devuelve las posibles formas en que el FP puede aparecer como sufijo
        en la carpeta `Resultados_FP_<fp>`. Las carpetas existentes usan
        '0', '0.25', '0.5', '0.85', '1' (sin .0 final), mientras que el combo
        del perfil entrega '0.0', '0.25', '0.5', '0.85', '1.0'. Probamos varias.
        """
        keys = [fp]
        try:
            f = float(fp)
            if f.is_integer():
                keys.append(str(int(f)))    # '0.0' -> '0', '1.0' -> '1'
            keys.append(f"{f:g}")           # normalización numérica
        except ValueError:
            pass
        # de-dup conservando orden
        seen = set(); out = []
        for k in keys:
            if k not in seen:
                seen.add(k); out.append(k)
        return out

    def _find_hil_files(self, fp, tipo):
        """
        Busca archivos HIL_*.csv en
            Resultados_Perfiles_Carga/Resultados_FP_<fp>/<tipo>/
        Maneja capitalización inconsistente del subdirectorio del tipo
        (Industrial / INDUSTRIAL, residencial / RESIDENCIAL).
        """
        if not os.path.isdir(RESULTADOS_HIL_DIR):
            return []

        # Resolver la carpeta Resultados_FP_<fp> probando varias normalizaciones
        fp_root = None
        for key in self._fp_resultados_keys(fp):
            cand = os.path.join(RESULTADOS_HIL_DIR, f"Resultados_FP_{key}")
            if os.path.isdir(cand):
                fp_root = cand
                break
        if fp_root is None:
            return []

        # Resolver la subcarpeta del tipo de carga (case-insensitive)
        target = tipo.lower()
        tipo_dir = None
        try:
            for entry in os.listdir(fp_root):
                full = os.path.join(fp_root, entry)
                if os.path.isdir(full) and entry.lower() == target:
                    tipo_dir = full
                    break
        except OSError:
            return []
        if tipo_dir is None:
            return []

        return sorted(glob.glob(os.path.join(tipo_dir, "HIL_*.csv")))

    def cargar_datos(self):
        fp   = self.fp_var.get()
        tipo = self.tipo_var.get()

        fp_dir   = os.path.join(PERFILES_DIR, f"FP_{fp}")
        csv_path = os.path.join(fp_dir, f"perfil_{tipo}_FP{fp}.csv")

        if not os.path.exists(csv_path):
            messagebox.showerror(
                "Archivo no encontrado",
                f"No existe:\n{csv_path}\n\n"
                "Verifica que el FP y tipo seleccionados tengan CSV generado."
            )
            return

        self.perfil_df = pd.read_csv(csv_path)
        self._plot_perfil()

        # Buscar archivos HIL dentro de Resultados_Perfiles_Carga/Resultados_FP_<fp>/<tipo>/
        hil_files = self._find_hil_files(fp, tipo)
        self.hil_combo["values"] = hil_files
        self.hil_path_var.set(hil_files[0] if hil_files else "")

        if self.inst is not None:
            self.btn_run.config(state="normal")

        self._set_status(
            f"Perfil cargado: FP={fp} | {tipo.capitalize()} | "
            f"{len(self.perfil_df)} muestras"
            + (f" | {len(hil_files)} archivo(s) HIL disponibles" if hil_files else " | Sin HIL")
        )

    def _plot_perfil(self):
        df   = self.perfil_df
        t    = df["Time"].values
        p    = df["P"].values
        q    = df["Q"].values
        tipo = self.tipo_var.get()
        fp   = self.fp_var.get()
        col  = C_RES if tipo == "residencial" else C_IND

        ax_p, ax_q = self.ax_perf_p, self.ax_perf_q
        ax_p.cla(); ax_q.cla()

        # P
        ax_p.fill_between(t, p, alpha=0.15, color=col)
        ax_p.plot(t, p, color=col, lw=1.6, label="P [pu]")
        ax_p.axhline(p.mean(), color=col, ls="--", lw=1.0, alpha=0.75,
                     label=f"P̄ = {p.mean():.3f} pu")
        ax_p.set_title(
            f"Potencia Activa — {tipo.capitalize()} | FP = {fp}",
            fontsize=9, fontweight="bold"
        )
        ax_p.set_ylabel("P [pu]", fontsize=8)
        ax_p.legend(fontsize=7, loc="upper right")
        ax_p.grid(True, linestyle=":", alpha=0.4)
        ax_p.tick_params(labelsize=7)

        # Q
        ax_q.fill_between(t, q, alpha=0.15, color=C_Q)
        ax_q.plot(t, q, color=C_Q, lw=1.6, label="Q [pu]")
        ax_q.axhline(q.mean(), color=C_Q, ls="--", lw=1.0, alpha=0.75,
                     label=f"Q̄ = {q.mean():.3f} pu")
        ax_q.set_title("Potencia Reactiva", fontsize=9, fontweight="bold")
        ax_q.set_ylabel("Q [pu]", fontsize=8)
        ax_q.set_xlabel("Tiempo [s]", fontsize=8)
        ax_q.legend(fontsize=7, loc="upper right")
        ax_q.grid(True, linestyle=":", alpha=0.4)
        ax_q.tick_params(labelsize=7)

        self.fig_perf.tight_layout()
        self.canvas_perf.draw()

    # ══════════════════════════════════════════════════════════════════════
    # LÓGICA — DINÁMICA HIL
    # ══════════════════════════════════════════════════════════════════════

    def cargar_hil(self):
        path = self.hil_path_var.get()
        if not path or not os.path.exists(path):
            messagebox.showerror(
                "Archivo no encontrado",
                f"No existe:\n{path}\n\nSelecciona un archivo HIL válido."
            )
            return

        df = pd.read_csv(path)

        # Downsample si supera el límite de puntos
        if len(df) > PLOT_MAX_PTS:
            step = max(1, len(df) // PLOT_MAX_PTS)
            df   = df.iloc[::step].reset_index(drop=True)

        self.hil_df = df
        self._plot_hil(os.path.basename(path))
        self._set_status(
            f"HIL cargado: {os.path.basename(path)} | "
            f"{len(df)} puntos graficados"
        )

    def _plot_hil(self, title=""):
        df   = self.hil_df
        cols = [c for c in df.columns if c.lower() != "time"]
        t    = df["Time"].values

        colors = [C_IND, C_RES, "#F0A500", C_V]
        axes   = self.axes_hil.flat

        for ax in self.axes_hil.flat:
            ax.cla()

        for i, ax in enumerate(self.axes_hil.flat):
            if i < len(cols):
                col   = cols[i]
                color = colors[i % len(colors)]
                ax.plot(t, df[col].values, color=color, lw=0.9)
                ax.set_title(col.replace("_", " "), fontsize=8, fontweight="bold")
                ax.set_xlabel("Tiempo [s]", fontsize=7)
                ax.set_ylabel(col.split("_")[0], fontsize=7)
                ax.grid(True, linestyle=":", alpha=0.4)
                ax.tick_params(labelsize=7)
            else:
                ax.set_visible(False)

        self.fig_hil.suptitle(title, fontsize=8, color="#555")
        self.fig_hil.tight_layout()
        self.canvas_hil.draw()

    # ══════════════════════════════════════════════════════════════════════
    # LÓGICA — CONEXIÓN USB
    # ══════════════════════════════════════════════════════════════════════

    def conectar_usb(self):
        if not PYVISA_OK:
            messagebox.showwarning(
                "pyvisa no instalado",
                "Instala las dependencias:\n  pip install pyvisa pyvisa-py"
            )
            return
        try:
            rm        = pyvisa.ResourceManager()
            self.inst = rm.open_resource(self.usb_var.get())
            self.inst.timeout = 5000
            idn = self.inst.query("*IDN?").strip()
            self._set_status(f"USB conectado: {idn}")
            if self.perfil_df is not None:
                self.btn_run.config(state="normal")
        except Exception as e:
            messagebox.showerror("Error USB", str(e))
            self.inst = None

    # ══════════════════════════════════════════════════════════════════════
    # LÓGICA — ENVÍO Y LECTURA DL3000 (hilo de trabajo)
    # ══════════════════════════════════════════════════════════════════════

    def iniciar_envio(self):
        if self.perfil_df is None:
            messagebox.showwarning("Sin perfil", "Carga un perfil de carga primero.")
            return
        if self.inst is None:
            messagebox.showwarning("Sin conexión USB", "Conecta el DL3000 por USB primero.")
            return

        self._running = True
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.nb.select(2)   # ir al tab de hardware

        threading.Thread(target=self._worker_dl3000, daemon=True).start()

    def _worker_dl3000(self):
        eth_sock = None
        try:
            # Configurar la carga
            self.inst.write("*RST")
            time.sleep(1.0)
            self.inst.write(":SOUR:FUNC CURR")

            df     = self.perfil_df
            t_vals = df["Time"].values
            p_vals = df["P"].values

            # Escalar P [pu] → corriente [0, I_max A]
            I_max  = self.imax_var.get()
            p_norm = p_vals / max(p_vals.max(), 1e-9)
            I_send = p_norm * I_max

            # Abrir socket Ethernet si está en modo "en vivo"
            if self.eth_live_var.get():
                eth_sock = self._abrir_socket()

            self.inst.write(":SOUR:INP:STAT 1")

            SETTLE_S = 0.08            # delay tras setpoint antes de medir
            POLL_S   = 0.05            # granularidad del wait (Detener responde rápido)

            ciclo = 0
            while self._running:
                ciclo += 1
                self._hw_data = {"t": [], "v": [], "i": []}

                speed = max(float(self.speed_var.get() or 1.0), 1e-3)
                t0    = time.perf_counter()

                for idx, (t, i_set) in enumerate(zip(t_vals, I_send)):
                    if not self._running:
                        break

                    # Esperar hasta que toque este punto según la columna Time
                    target = float(t) / speed
                    while self._running:
                        remaining = target - (time.perf_counter() - t0)
                        if remaining <= 0:
                            break
                        time.sleep(min(remaining, POLL_S))
                    if not self._running:
                        break

                    # Enviar corriente y dejar asentar
                    self.inst.write(f":SOUR:CURR:LEV:IMM {i_set:.5f}")
                    time.sleep(SETTLE_S)

                    # Leer voltaje y corriente
                    v_med = float(self.inst.query(":MEAS:VOLT?").strip())
                    i_med = float(self.inst.query(":MEAS:CURR?").strip())

                    self._hw_data["t"].append(t)
                    self._hw_data["v"].append(v_med)
                    self._hw_data["i"].append(i_med)

                    # Envío Ethernet en tiempo real
                    if eth_sock is not None:
                        try:
                            pkt = f"{t:.4f},{v_med:.6f},{i_med:.6f}\n"
                            eth_sock.sendall(pkt.encode())
                        except Exception:
                            pass

                    # Actualizar gráfica cada 5 puntos
                    if idx % 5 == 0:
                        self.after(0, self._update_hw_plot)

                    self._set_status(
                        f"Ciclo {ciclo} | Punto {idx + 1}/{len(t_vals)} "
                        f"(t={t:.1f}s, vel ×{speed:g}) — "
                        f"I_set={i_set:.4f} A | V={v_med:.3f} V | I={i_med:.4f} A"
                    )

                # Guardar CSV del ciclo
                self._guardar_csv_hw(ciclo)

                if not self.loop_var.get():
                    break

        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror("Error hardware", str(err)))
        finally:
            # Apagar la carga de forma segura
            try:
                self.inst.write(":SOUR:INP:STAT 0")
                self.inst.write(":SOUR:CURR:LEV:IMM 0")
            except Exception:
                pass
            if eth_sock:
                try:
                    eth_sock.close()
                except Exception:
                    pass

            self._running = False
            self.after(0, lambda: self.btn_run.config(state="normal"))
            self.after(0, lambda: self.btn_stop.config(state="disabled"))
            self._set_status("Envío finalizado. Carga DL3000 apagada.")

    def _update_hw_plot(self):
        d = self._hw_data
        if not d["t"]:
            return
        ax_v, ax_i = self.ax_hw_v, self.ax_hw_i
        ax_v.cla(); ax_i.cla()

        ax_v.plot(d["t"], d["v"], color=C_V, lw=1.3, label="V medido")
        ax_v.set_ylabel("Voltaje (V)", fontsize=8)
        ax_v.set_title("Voltaje medido — DL3000", fontsize=9, fontweight="bold")
        ax_v.grid(True, linestyle=":", alpha=0.4)
        ax_v.tick_params(labelsize=7)

        ax_i.plot(d["t"], d["i"], color=C_I, lw=1.3, label="I medida")
        ax_i.set_ylabel("Corriente (A)", fontsize=8)
        ax_i.set_xlabel("Tiempo [s]", fontsize=8)
        ax_i.set_title("Corriente medida — DL3000", fontsize=9, fontweight="bold")
        ax_i.grid(True, linestyle=":", alpha=0.4)
        ax_i.tick_params(labelsize=7)

        self.fig_hw.tight_layout()
        self.canvas_hw.draw()

    def _guardar_csv_hw(self, ciclo=1):
        d = self._hw_data
        if not d["t"]:
            return
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp    = self.fp_var.get()
        tipo  = self.tipo_var.get()
        fname = os.path.join(
            DATOS_DIR,
            f"medicion_{tipo}_FP{fp}_ciclo{ciclo}_{ts}.csv"
        )
        with open(fname, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Time_s", "Voltaje_V", "Corriente_A"])
            for t, v, i in zip(d["t"], d["v"], d["i"]):
                w.writerow([f"{t:.4f}", f"{v:.6f}", f"{i:.6f}"])
        self._set_status(f"CSV guardado: {os.path.basename(fname)}")

    def detener(self):
        self._running = False
        self._set_status("Deteniendo... (espera el punto actual)")

    # ══════════════════════════════════════════════════════════════════════
    # LÓGICA — ETHERNET (envío post-medición)
    # ══════════════════════════════════════════════════════════════════════

    def _abrir_socket(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((self.eth_host_var.get(), self.eth_port_var.get()))
            self._set_status(
                f"Ethernet conectado a {self.eth_host_var.get()}:{self.eth_port_var.get()}"
            )
            return s
        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror(
                "Error Ethernet", f"No se pudo conectar:\n{err}"
            ))
            return None

    def enviar_ethernet_post(self):
        d = self._hw_data
        if not d["t"]:
            messagebox.showwarning(
                "Sin datos",
                "Primero ejecuta una medición con el DL3000."
            )
            return
        threading.Thread(target=self._worker_ethernet_post, daemon=True).start()

    def _worker_ethernet_post(self):
        sock = self._abrir_socket()
        if sock is None:
            return
        try:
            d = self._hw_data
            for t, v, i in zip(d["t"], d["v"], d["i"]):
                pkt = f"{t:.4f},{v:.6f},{i:.6f}\n"
                sock.sendall(pkt.encode())
            self._set_status(
                f"Ethernet: {len(d['t'])} puntos enviados a "
                f"{self.eth_host_var.get()}:{self.eth_port_var.get()}"
            )
        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror("Error Ethernet", str(err)))
        finally:
            sock.close()

    # ── Utilitario ──────────────────────────────────────────────────────────
    def _set_status(self, msg):
        self.after(0, lambda m=msg: self.status_var.set(m))


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()
