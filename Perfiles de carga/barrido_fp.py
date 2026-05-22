import os
import numpy as np
import csv
from load_profile_generator import generar_perfil

def main():
    # Carpeta donde se guardarán los resultados del barrido
    out_dir = "barrido_fp_resultados"
    
    # Obtener la ruta absoluta basada en la ubicación de este script
    base_path = os.path.dirname(os.path.abspath(__file__))
    full_out_dir = os.path.join(base_path, out_dir)
    
    os.makedirs(full_out_dir, exist_ok=True)
    
    # Valores de Factor de Potencia a simular (0 a 1 con delta de 0.05)
    factores_de_potencia = np.round(np.arange(0.0, 1.05, 0.05), 2).tolist()
    
    for fp_val in factores_de_potencia:
        print(f"\n--- Generando perfiles para FP = {fp_val} ---")
        
        # Físicamente, un Factor de Potencia de exactamente 0 con una Potencia Activa (P)
        # mayor a cero requeriría una Potencia Aparente (S) infinita. (S = P / 0)
        # Para evitar que el software colapse con errores de "Division by Zero",
        # si se pide FP=0, utilizaremos un valor muy cercano a cero (0.001).
        fp_safe = max(fp_val, 0.001)
        
        for tipo in ["residencial", "industrial"]:
            # 1. Generamos el perfil original con V_nom = 120V
            # P_max = 5000 W para residencial, 50000 W para industrial
            V_nom = 120
            P_max = 5000 if tipo == "residencial" else 50000
            
            perfil = generar_perfil(tipo, V_nom, P_max)
            
            # 2. Sobrescribimos el Factor de Potencia por el valor estable del barrido (constante)
            perfil["fp"] = np.full(len(perfil["t_s"]), fp_safe)
            
            # Recalculamos S y Q con el nuevo FP
            perfil["S"] = perfil["P"] / perfil["fp"]
            perfil["Q"] = np.sqrt(np.clip(perfil["S"]**2 - perfil["P"]**2, 0, None))
            
            # Base pu = S_max (potencia aparente máxima).
            # Garantiza P_pu ∈ [0,1] y Q_pu ∈ [0,1] para cualquier FP,
            # preservando la relación triangular P-Q.
            S_max = perfil["S"].max()
            P_pu = perfil["P"] / S_max
            Q_pu = perfil["Q"] / S_max
            
            # 3. Exportamos Time, P y Q en un solo archivo por carpeta de FP
            fp_dir = os.path.join(full_out_dir, f"FP_{fp_val}")
            os.makedirs(fp_dir, exist_ok=True)
            
            # Nombre solicitado: perfil X (tipo) y factor de potencia
            nombre_archivo = os.path.join(fp_dir, f"perfil_{tipo}_FP{fp_val}.csv")
            
            with open(nombre_archivo, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["Time", "P", "Q"])
                for t, p_v, q_v in zip(perfil["t_s"], P_pu, Q_pu):
                    w.writerow([f"{t:.1f}", f"{p_v:.4f}", f"{q_v:.4f}"])
            
    print(f"\n[ÉXITO] ¡Barrido finalizado! Todos los archivos CSV ({len(factores_de_potencia)*2} en total)")
    print(f"Solo contienen P y Q en pu. Fueron guardados en:\n{full_out_dir}")

if __name__ == "__main__":
    main()
