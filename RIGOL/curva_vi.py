"""
Curva V-I con RIGOL DL3021
--------------------------
Hace un barrido de corriente en modo CC y mide voltaje en cada punto.
Guarda los resultados en un CSV y grafica la curva V-I + P-I.
"""

import pyvisa
import time
import csv
import matplotlib.pyplot as plt
from datetime import datetime

# ─────────────────────────────────────────
# CONFIGURACIÓN — ajusta estos parámetros
# ─────────────────────────────────────────
RESOURCE_ID  = 'USB0::0x1AB1::0x0E11::DL3A243500940::INSTR'  # <-- tu ID
I_INICIO     = 5    # Corriente inicial (A)
I_FIN        = 5       # Corriente final (A)
I_PASO       = 0.1    # Paso de corriente (A)
ESPERA       = 60    # Segundos de espera entre puntos (estabilización)
RANGO_CURR   = 40     # Rango de corriente del DL3021 (40 A max)
CSV_SALIDA   = "curva_vi.csv"
# ─────────────────────────────────────────

def conectar(resource_id):
    rm = pyvisa.ResourceManager()
    inst = rm.open_resource(resource_id)
    inst.timeout = 5000  # 5 s timeout
    idn = inst.query("*IDN?").strip()
    print(f"✔ Conectado: {idn}\n")
    return inst

def configurar_carga(inst, rango):
    inst.write("*RST")                          # Reset a valores de fábrica
    time.sleep(2)
    inst.write(":SOUR:FUNC CURR")              # Modo Corriente Constante (CC)
    inst.write(f":SOUR:CURR:RANG {rango}")     # Rango de corriente

def medir_punto(inst, corriente):
    inst.write(f":SOUR:CURR:LEV:IMM {corriente:.4f}")
    time.sleep(ESPERA)
    v = float(inst.query(":MEAS:VOLT?").strip())
    i = float(inst.query(":MEAS:CURR?").strip())
    p = float(inst.query(":MEAS:POW?").strip())
    return v, i, p

def guardar_csv(datos, nombre_archivo):
    with open(nombre_archivo, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Corriente_set (A)", "Voltaje (V)", "Corriente_med (A)", "Potencia (W)"])
        writer.writerows(datos)
    print(f"\n✔ Datos guardados en: {nombre_archivo}")

def graficar(datos):
    i_set = [d[0] for d in datos]
    voltajes = [d[1] for d in datos]
    potencias = [d[3] for d in datos]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    fig.suptitle("Curva V-I y P-I — RIGOL DL3021", fontsize=14, fontweight="bold")

    ax1.plot(i_set, voltajes, "o-", color="#2563EB", linewidth=2, markersize=5)
    ax1.set_ylabel("Voltaje (V)")
    ax1.set_title("Curva V-I")
    ax1.grid(True, linestyle="--", alpha=0.6)

    ax2.plot(i_set, potencias, "s-", color="#DC2626", linewidth=2, markersize=5)
    ax2.set_xlabel("Corriente (A)")
    ax2.set_ylabel("Potencia (W)")
    ax2.set_title("Curva P-I")
    ax2.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    nombre_fig = f"curva_vi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(nombre_fig, dpi=150)
    print(f"✔ Gráfica guardada en: {nombre_fig}")
    plt.show()

def main():
    inst = conectar(RESOURCE_ID)

    try:
        configurar_carga(inst, RANGO_CURR)

        # Encender la carga
        inst.write(":SOUR:INP:STAT 1")
        print("▶ Carga encendida. Iniciando barrido...\n")
        print(f"{'I_set (A)':>12} {'V (V)':>10} {'I_med (A)':>12} {'P (W)':>10}")
        print("-" * 48)

        datos = []
        corriente = I_INICIO
        while corriente <= I_FIN + 1e-9:
            v, i, p = medir_punto(inst, corriente)
            print(f"{corriente:>12.2f} {v:>10.4f} {i:>12.4f} {p:>10.4f}")
            datos.append((corriente, v, i, p))
            corriente = round(corriente + I_PASO, 6)

        print("\n■ Barrido completo.")

    finally:
        # Apagar la carga siempre, incluso si hay error
        inst.write(":SOUR:INP:STAT 0")
        inst.write(":SOUR:CURR:LEV:IMM 0")
        inst.close()
        print("■ Carga apagada y recurso cerrado.")

    guardar_csv(datos, CSV_SALIDA)
    graficar(datos)

if __name__ == "__main__":
    main()
