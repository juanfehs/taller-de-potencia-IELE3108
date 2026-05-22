"""
Generador de Perfiles de Carga para Typhoon HIL
================================================
Genera perfiles de 24h (resolución 15 min = 96 muestras) para cargas
residenciales e industriales. Exporta CSV compatible con Typhoon HIL
CPL (Controlled Power Load): columnas time [s], P [W], Q [VAR].

También genera CSV extendido con: time, V [V], I [A], P [W], Q [VAR], FP, S [VA].

Parámetros de entrada:
  --V_nom     Tensión nominal de la carga [V RMS, fase-neutro o fase-fase]
  --P_max_res Potencia activa máxima residencial [W]
  --P_max_ind Potencia activa máxima industrial [W]
  --freq      Frecuencia de muestreo de salida [Hz] — para el eje time del CSV
  --exportar  Exportar CSVs
  --guardar_fig Guardar figura PNG

Uso:
  python load_profile_generator.py --V_nom 120 --P_max_res 5000 --P_max_ind 50000
  python load_profile_generator.py --V_nom 208 --P_max_res 8000 --P_max_ind 80000 --exportar

Autor: JF — IELE, Universidad de los Andes
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import argparse
import csv

# ══════════════════════════════════════════════════════════════════════════════
# PARÁMETROS DE TIEMPO
# ══════════════════════════════════════════════════════════════════════════════

N_MUESTRAS  = 72          # 12 min / 10s = 72 muestras
T_TOTAL_S   = 720         # 12 min en segundos (12 * 60)
T_STEP_S    = 10          # 10 s por muestra
HORAS_REF   = list(range(25))          # knots de interpolación


# ══════════════════════════════════════════════════════════════════════════════
# PERFILES BASE NORMALIZADOS [pu]
# ══════════════════════════════════════════════════════════════════════════════

def _interpolar(horas_knot, vals_knot):
    """Interpolación lineal sobre 96 puntos en [0, 24)."""
    t = np.linspace(0, 24, N_MUESTRAS, endpoint=False)
    return np.interp(t, horas_knot, vals_knot)


# ── Potencia activa P ─────────────────────────────────────────────────────────

def P_residencial_pu():
    h = [0,   1,   2,   3,   4,   5,   6,   7,   8,   9,
         10,  11,  12,  13,  14,  15,  16,  17,  18,  19,
         20,  21,  22,  23,  24]
    v = [0.25,0.20,0.18,0.17,0.18,0.22,0.40,0.80,0.70,0.55,
         0.50,0.52,0.58,0.55,0.50,0.48,0.52,0.60,0.75,0.90,
         1.00,0.95,0.80,0.50,0.25]
    p = _interpolar(h, v)
    np.random.seed(42)
    p = np.clip(p + np.random.normal(0, 0.012, N_MUESTRAS), 0.05, 1.0)
    return p / p.max()


def P_industrial_pu():
    h = [0,   1,   2,   3,   4,   5,   6,   7,   8,   9,
         10,  11,  12,  13,  14,  15,  16,  17,  18,  19,
         20,  21,  22,  23,  24]
    v = [0.15,0.15,0.15,0.15,0.15,0.20,0.65,0.95,1.00,0.98,
         0.97,0.96,0.85,0.90,0.97,0.98,0.96,0.94,0.88,0.80,
         0.65,0.40,0.20,0.15,0.15]
    p = _interpolar(h, v)
    p[int(24 * N_MUESTRAS / 96)] = min(p[int(24 * N_MUESTRAS / 96)] * 1.12, 1.0)
    p[int(52 * N_MUESTRAS / 96)] = min(p[int(52 * N_MUESTRAS / 96)] * 1.08, 1.0)
    np.random.seed(7)
    p = np.clip(p + np.random.normal(0, 0.008, N_MUESTRAS), 0.05, 1.0)
    return p / p.max()


# ── Factor de potencia variable por hora ──────────────────────────────────────
#
# Residencial: FP bajo de noche (iluminación, TV en standby),
#              sube de mañana (electrodomésticos resistivos),
#              cae levemente a mediodía (A/C, cargas inductivas),
#              sube al anochecer, cae con la carga nocturna mixta.
#
# Industrial:  FP muy bajo en arranque (motores),
#              se recupera en operación nominal,
#              cae al final del turno (variadores, motores parciales).

def FP_residencial():
    h = [0,   2,   4,   6,   7,   8,   10,  12,  14,  16,
         18,  19,  20,  21,  22,  24]
    v = [0.82,0.80,0.80,0.83,0.88,0.92,0.90,0.87,0.88,0.90,
         0.91,0.93,0.92,0.88,0.85,0.82]
    fp = _interpolar(h, v)
    np.random.seed(11)
    fp = np.clip(fp + np.random.normal(0, 0.005, N_MUESTRAS), 0.75, 0.98)
    return fp


def FP_industrial():
    h = [0,   5,   6,   7,   8,   10,  12,  13,  14,  16,
         18,  20,  21,  22,  23,  24]
    v = [0.80,0.80,0.72,0.88,0.93,0.95,0.92,0.88,0.94,0.95,
         0.93,0.88,0.82,0.80,0.80,0.80]
    fp = _interpolar(h, v)
    np.random.seed(13)
    fp = np.clip(fp + np.random.normal(0, 0.004, N_MUESTRAS), 0.70, 0.98)
    return fp


# ── Perfil de tensión (pequeñas variaciones en la red) ───────────────────────

def V_perfil(V_nom):
    """
    Variación de tensión ±3% alrededor de V_nom siguiendo
    la demanda (tensión cae cuando sube la carga).
    """
    h = [0,   6,   7,   8,   12,  14,  18,  20,  21,  24]
    v = [1.02,1.01,0.99,0.98,1.00,1.01,0.99,0.97,0.98,1.02]
    vpu = _interpolar(h, v)
    np.random.seed(3)
    vpu = np.clip(vpu + np.random.normal(0, 0.002, N_MUESTRAS), 0.95, 1.05)
    return vpu * V_nom


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL DE GENERACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def generar_perfil(tipo: str, V_nom: float, P_max: float) -> dict:
    """
    Genera el perfil completo de una carga.

    Parámetros
    ----------
    tipo  : 'residencial' | 'industrial'
    V_nom : tensión nominal [V RMS]
    P_max : potencia activa máxima [W]

    Retorna
    -------
    dict con arrays numpy de 96 muestras + estadísticos resumen
    """
    if tipo == "residencial":
        P_pu = P_residencial_pu()
        fp   = FP_residencial()
    elif tipo == "industrial":
        P_pu = P_industrial_pu()
        fp   = FP_industrial()
    else:
        raise ValueError(f"Tipo '{tipo}' no reconocido.")

    t_s  = np.arange(N_MUESTRAS) * T_STEP_S      # tiempo en segundos [0..86400)
    t_h  = t_s / 3600                             # tiempo en horas

    P    = P_pu * P_max                           # potencia activa [W]
    S    = P / fp                                 # potencia aparente [VA]
    Q    = np.sqrt(np.clip(S**2 - P**2, 0, None)) # potencia reactiva [VAR] (inductiva)
    V    = V_perfil(V_nom)                        # tensión [V RMS]
    I    = S / V                                  # corriente [A RMS]

    return {
        "tipo"      : tipo,
        "V_nom"     : V_nom,
        "P_max"     : P_max,
        # arrays
        "t_s"       : t_s,
        "t_h"       : t_h,
        "V"         : V,
        "I"         : I,
        "P"         : P,
        "Q"         : Q,
        "S"         : S,
        "fp"        : fp,
        # estadísticos
        "P_media"   : P.mean(),
        "Q_media"   : Q.mean(),
        "I_max_real": I.max(),
        "I_media"   : I.mean(),
        "FC"        : P.mean() / P_max,
        "fp_medio"  : fp.mean(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# EXPORTACIÓN CSV — FORMATO TYPHOON HIL CPL
# ══════════════════════════════════════════════════════════════════════════════

def exportar_typhoon(perfil: dict, nombre: str = None):
    """
    CSV mínimo para Typhoon HIL CPL:
        time [s]  |  P [W]  |  Q [VAR]
    La primera fila es el header; Typhoon lo lee directamente.
    """
    if nombre is None:
        nombre = f"typhoon_{perfil['tipo']}_Vnom{perfil['V_nom']:.0f}V.csv"

    with open(nombre, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "P", "Q"])
        for t, P, Q in zip(perfil["t_s"], perfil["P"], perfil["Q"]):
            w.writerow([f"{t:.1f}", f"{P:.4f}", f"{Q:.4f}"])

    print(f"[✓] Typhoon CPL CSV: {nombre}  ({N_MUESTRAS} filas)")
    return nombre


def exportar_completo(perfil: dict, nombre: str = None):
    """
    CSV extendido con todas las variables eléctricas:
        time [s] | V [V] | I [A] | P [W] | Q [VAR] | S [VA] | FP
    """
    if nombre is None:
        nombre = f"perfil_completo_{perfil['tipo']}_Vnom{perfil['V_nom']:.0f}V.csv"

    with open(nombre, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "V_V", "I_A", "P_W", "Q_VAR", "S_VA", "FP"])
        for t, V, I, P, Q, S, fp in zip(
                perfil["t_s"], perfil["V"], perfil["I"],
                perfil["P"],   perfil["Q"], perfil["S"], perfil["fp"]):
            w.writerow([f"{t:.1f}", f"{V:.4f}", f"{I:.4f}",
                        f"{P:.4f}", f"{Q:.4f}", f"{S:.4f}", f"{fp:.4f}"])

    print(f"[✓] CSV extendido:   {nombre}  ({N_MUESTRAS} filas)")
    return nombre


# ══════════════════════════════════════════════════════════════════════════════
# VISUALIZACIÓN
# ══════════════════════════════════════════════════════════════════════════════

COLORES = {"residencial": "#E8523A", "industrial": "#2E86AB"}
XTICKS  = range(0, 25, 2)


def _ax_style(ax, ylabel, title, ylim=None):
    ax.set_xlabel("Hora del día [h]", fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_title(title, fontsize=9, fontweight="bold")
    ax.set_xlim(0, 24)
    ax.set_xticks(XTICKS)
    ax.tick_params(labelsize=7)
    ax.grid(True, linestyle=":", alpha=0.45)
    if ylim:
        ax.set_ylim(*ylim)


def graficar(perfiles: list, guardar: bool = False, nombre: str = "perfiles_carga"):
    n   = len(perfiles)
    fig = plt.figure(figsize=(16, 6 * n))
    fig.suptitle("Perfiles de Carga — Generador para Typhoon HIL",
                 fontsize=13, fontweight="bold", y=1.01)

    for idx, p in enumerate(perfiles):
        color = COLORES[p["tipo"]]
        label = p["tipo"].capitalize()
        t     = p["t_h"]
        base  = idx * 10   # posición en gridspec

        gs = gridspec.GridSpec(2, 3, figure=fig,
                               top=1 - idx * (1/n) - 0.02,
                               bottom=1 - (idx+1) * (1/n) + 0.06,
                               hspace=0.45, wspace=0.35)

        # ── P y Q ──────────────────────────────────────────────────────────
        ax_pq = fig.add_subplot(gs[0, 0])
        ax_pq.fill_between(t, p["P"] / 1e3, alpha=0.18, color=color)
        ax_pq.plot(t, p["P"] / 1e3, color=color, lw=1.8, label="P [kW]")
        ax_pq.fill_between(t, p["Q"] / 1e3, alpha=0.10, color="gray")
        ax_pq.plot(t, p["Q"] / 1e3, color="gray", lw=1.4, ls="--", label="Q [kVAR]")
        ax_pq.axhline(p["P_media"] / 1e3, color=color, ls=":", lw=1.0,
                      label=f"P̄={p['P_media']/1e3:.2f} kW")
        ax_pq.legend(fontsize=7, loc="upper left")
        _ax_style(ax_pq, "kW / kVAR", f"{label} — Potencia activa y reactiva")

        # ── S y FP ─────────────────────────────────────────────────────────
        ax_sfp = fig.add_subplot(gs[0, 1])
        ax2    = ax_sfp.twinx()
        l1, = ax_sfp.plot(t, p["S"] / 1e3, color=color, lw=1.8, label="S [kVA]")
        l2, = ax2.plot(t, p["fp"], color="#F0A500", lw=1.5, ls="-.", label="FP")
        ax2.set_ylim(0.60, 1.05)
        ax2.set_ylabel("Factor de potencia", fontsize=8, color="#F0A500")
        ax2.tick_params(labelsize=7, colors="#F0A500")
        ax_sfp.legend(handles=[l1, l2], fontsize=7, loc="upper left")
        _ax_style(ax_sfp, "kVA", f"{label} — Potencia aparente y FP")

        # ── Tensión ────────────────────────────────────────────────────────
        ax_v = fig.add_subplot(gs[0, 2])
        ax_v.fill_between(t, p["V"], alpha=0.15, color="#5B8C5A")
        ax_v.plot(t, p["V"], color="#5B8C5A", lw=1.8)
        ax_v.axhline(p["V_nom"], color="black", ls="--", lw=0.9,
                     alpha=0.6, label=f"$V_{{nom}}$ = {p['V_nom']:.0f} V")
        ax_v.legend(fontsize=7)
        _ax_style(ax_v, "V [V]", f"{label} — Tensión de carga",
                  ylim=(p["V_nom"] * 0.92, p["V_nom"] * 1.08))

        # ── Corriente ─────────────────────────────────────────────────────
        ax_i = fig.add_subplot(gs[1, 0])
        ax_i.fill_between(t, p["I"], alpha=0.18, color=color)
        ax_i.plot(t, p["I"], color=color, lw=1.8)
        ax_i.axhline(p["I_max_real"], color="red", ls="-.", lw=1.0,
                     alpha=0.75, label=f"$I_{{max}}$={p['I_max_real']:.2f} A")
        ax_i.axhline(p["I_media"], color=color, ls=":", lw=1.0,
                     label=f"$\\bar{{I}}$={p['I_media']:.2f} A")
        ax_i.legend(fontsize=7)
        _ax_style(ax_i, "I [A]", f"{label} — Corriente de carga")

        # ── CSV preview (P y Q como barras pequeñas) ───────────────────────
        ax_bar = fig.add_subplot(gs[1, 1:])
        horas_repr = np.arange(0, 24, 1)        # 24 puntos representativos
        idx_repr   = (horas_repr * (N_MUESTRAS / 24)).astype(int)
        ax_bar.bar(horas_repr - 0.2, p["P"][idx_repr] / 1e3, width=0.35,
                   color=color, alpha=0.85, label="P [kW]")
        ax_bar.bar(horas_repr + 0.2, p["Q"][idx_repr] / 1e3, width=0.35,
                   color="gray", alpha=0.60, label="Q [kVAR]")
        ax_bar.set_xlabel("Hora del día [h]", fontsize=8)
        ax_bar.set_ylabel("kW / kVAR", fontsize=8)
        ax_bar.set_title(f"{label} — Vista horaria P y Q (preview CSV Typhoon)", fontsize=9, fontweight="bold")
        ax_bar.set_xlim(-0.8, 23.8)
        ax_bar.tick_params(labelsize=7)
        ax_bar.grid(True, axis="y", linestyle=":", alpha=0.4)
        ax_bar.legend(fontsize=7)

        # Resumen textual
        resumen = (f"FC={p['FC']:.3f}  |  FP̄={p['fp_medio']:.3f}  |  "
                   f"P_max={p['P_max']/1e3:.1f} kW  |  "
                   f"Q̄={p['Q_media']/1e3:.2f} kVAR  |  "
                   f"I_max={p['I_max_real']:.2f} A  |  V_nom={p['V_nom']:.0f} V")
        fig.text(0.5, 1 - (idx+1)*(1/n) + 0.03, resumen,
                 ha="center", fontsize=8, color="#444",
                 bbox=dict(boxstyle="round,pad=0.3", fc="#f5f5f5", ec="#ccc", lw=0.8))

    plt.tight_layout()
    if guardar:
        path = f"{nombre}.png"
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"[✓] Figura guardada: {path}")
    plt.show()


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Generador de perfiles de carga para Typhoon HIL (P, Q, V, I, FP variable)."
    )
    parser.add_argument("--V_nom",     type=float, required=True,
                        help="Tensión nominal de la carga [V RMS]. Ej: 120, 208, 480")
    parser.add_argument("--P_max_res", type=float, default=5000,
                        help="Potencia activa máxima residencial [W] (default: 5000)")
    parser.add_argument("--P_max_ind", type=float, default=50000,
                        help="Potencia activa máxima industrial [W] (default: 50000)")
    parser.add_argument("--exportar",    action="store_true",
                        help="Exportar CSVs para Typhoon HIL y extendido")
    parser.add_argument("--guardar_fig", action="store_true",
                        help="Guardar figura como PNG")
    parser.add_argument("--sin_grafica", action="store_true",
                        help="No mostrar gráfica")
    parser.add_argument("--outdir",    type=str, default=".",
                        help="Directorio de salida (default: .)")
    args = parser.parse_args()

    configs = [
        ("residencial", args.V_nom, args.P_max_res),
        ("industrial",  args.V_nom, args.P_max_ind),
    ]

    perfiles = []
    for tipo, V, P_max in configs:
        p = generar_perfil(tipo, V, P_max)
        perfiles.append(p)

        print(f"\n{'═'*52}")
        print(f"  PERFIL {tipo.upper()}")
        print(f"{'═'*52}")
        print(f"  V_nom          = {V:.1f} V")
        print(f"  P_max          = {P_max/1e3:.2f} kW")
        print(f"  P_media        = {p['P_media']/1e3:.4f} kW")
        print(f"  Q_media        = {p['Q_media']/1e3:.4f} kVAR")
        print(f"  I_max (real)   = {p['I_max_real']:.4f} A")
        print(f"  I_media        = {p['I_media']:.4f} A")
        print(f"  FP promedio    = {p['fp_medio']:.4f}")
        print(f"  Factor carga   = {p['FC']:.4f}")
        print(f"  Muestras       = {N_MUESTRAS}  (Δt = {T_STEP_S:.0f} s = 15 min)")

        if args.exportar:
            base = f"{args.outdir}/"
            exportar_typhoon(p,   base + f"typhoon_{tipo}_V{V:.0f}.csv")
            exportar_completo(p,  base + f"completo_{tipo}_V{V:.0f}.csv")

    if not args.sin_grafica:
        graficar(perfiles, guardar=args.guardar_fig,
                 nombre=f"{args.outdir}/perfiles_carga")


if __name__ == "__main__":
    main()
