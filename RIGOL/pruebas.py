import pyvisa
import time
import csv
import os
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")   # guardar sin abrir ventana (quitar si quieres ventana interactiva)

# ── Parámetros ────────────────────────────────────────────────────────────────
CSV_PATH  = r"C:\Users\Juan Felipe\OneDrive - Universidad de los andes\IELE\Semestres\VIII\Taller de Potencia\Datos de prueba\CorrienteN2\500A-0R_N2.csv"
ESPERA    = 1.0   # s  (tiempo de estabilización por punto)
RANGO_A   = 5     # A  (rango del DL3021; 5 A porque la fuente solo soporta 1 A)
I_MAX     = 1.0   # A  (corriente máxima que permite la fuente)
N_MAX     = 1000  # máximo número de puntos a aplicar del CSV

# ── 1. Leer corrientes desde el CSV (última columna: Corriente_DC_N2) ─────────
corrientes_csv = []
with open(CSV_PATH, newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)          # leer encabezado
    col_idx = len(header) - 1     # índice de la última columna
    print(f"Columna de corriente: '{header[col_idx]}'  (col {col_idx})")
    for row in reader:
        try:
            val = float(row[col_idx])
            corrientes_csv.append(val)
        except (ValueError, IndexError):
            pass  # ignorar filas mal formadas

print(f"Puntos leídos del CSV: {len(corrientes_csv)}")

# ── Escalado min-max → [0, I_MAX] ────────────────────────────────────────────
# Se toma el rango total del CSV y se mapea proporcionalmente al rango de la fuente
I_csv_min = min(corrientes_csv)
I_csv_max = max(corrientes_csv)
print(f"Rango original CSV: [{I_csv_min:.4f}, {I_csv_max:.4f}] A");
print(f"Rango escalado:     [0.0000, {I_MAX:.4f}] A  (escala: {I_MAX/(I_csv_max - I_csv_min):.6f} A/A)")

def escalar(v):
    """Mapea v desde el rango CSV a [0, I_MAX] (min-max normalization)."""
    v_norm = (v - I_csv_min) / (I_csv_max - I_csv_min)  # → [0, 1]
    return round(v_norm * I_MAX, 4)                       # → [0, I_MAX]

corrientes = [escalar(v) for v in corrientes_csv[:N_MAX]]
print(f"Puntos a usar (tras límite N_MAX={N_MAX}): {len(corrientes)}")

# ── 2. Conectar al instrumento ────────────────────────────────────────────────
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('USB0::0x1AB1::0x0E11::DL3A243500940::INSTR')
inst.timeout = 5000  # ms
print("\nInstrumento:", inst.query("*IDN?").strip())

# ── 3. Configurar modo CC ─────────────────────────────────────────────────────
inst.write("*RST")
time.sleep(2)                              # esperar reset
inst.write(":SOUR:FUNC CURR")             # modo Corriente Constante
inst.write(f":SOUR:CURR:RANG {RANGO_A}")   # rango de corriente
print(f"Corriente máxima a aplicar: {max(corrientes):.4f} A  (límite fuente: {I_MAX} A)")

# ── 4. Sweep siguiendo los valores del CSV ────────────────────────────────────
resultados = []  # lista de tuplas (I_set, V_med, I_med)

print(f"\n{'#':>6} {'I_set (A)':>10} {'V_med (V)':>12} {'I_med (A)':>12}")
print("-" * 44)

# Encender la carga con 0 A
inst.write(":SOUR:CURR:LEV:IMM 0.0000")
inst.write(":SOUR:INP:STAT 1")
time.sleep(0.5)

for idx, I_set in enumerate(corrientes):
    inst.write(f":SOUR:CURR:LEV:IMM {I_set:.4f}")  # fijar corriente
    time.sleep(ESPERA)                               # esperar estabilización

    V = float(inst.query(":MEAS:VOLT?").strip())
    I = float(inst.query(":MEAS:CURR?").strip())

    resultados.append((I_set, V, I))
    print(f"{idx+1:>6} {I_set:>10.4f} {V:>12.4f} {I:>12.4f}")

# ── 5. Apagar la carga de forma segura ───────────────────────────────────────
inst.write(":SOUR:INP:STAT 0")
inst.close()

print("\nSweep finalizado. Carga apagada.")
print(f"Total de puntos medidos: {len(resultados)}")

# ── 6. Graficar resultados ────────────────────────────────────────────────────
I_sets = [r[0] for r in resultados]
V_meds = [r[1] for r in resultados]
I_meds = [r[2] for r in resultados]
indices = list(range(1, len(resultados) + 1))

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
fig.suptitle("Sweep de corriente constante – RIGOL DL3021", fontsize=13, fontweight="bold")

# Panel superior: voltaje medido
ax1.plot(indices, V_meds, color="royalblue", linewidth=0.8, label="V medido")
ax1.set_ylabel("Voltaje (V)")
ax1.set_title("Voltaje medido")
ax1.legend(loc="upper right")
ax1.grid(True, linestyle="--", alpha=0.5)

# Panel inferior: corriente set vs medida
ax2.plot(indices, I_sets, color="darkorange", linewidth=0.8, label="I_set (escalada CSV)")
ax2.plot(indices, I_meds, color="forestgreen",  linewidth=0.8, linestyle="--", label="I_med (RIGOL)")
ax2.set_xlabel("Muestra #")
ax2.set_ylabel("Corriente (A)")
ax2.set_title("Corriente: referencia vs medida")
ax2.legend(loc="upper right")
ax2.grid(True, linestyle="--", alpha=0.5)

plt.tight_layout()

# Guardar figura junto al script
out_dir  = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(out_dir, "sweep_resultado.png")
fig.savefig(out_path, dpi=150)
print(f"Gráfica guardada en: {out_path}")
