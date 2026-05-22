# Taller de Potencia — IELE3108
**Universidad de los Andes · Ingeniería Eléctrica · Semestre VIII**

Proyecto de laboratorio para el control y monitoreo de cargas eléctricas usando el instrumento RIGOL DL3021, simulación HIL con Typhoon y comunicación Ethernet hacia un SCADA externo.

---

## Descripción general

El sistema integra tres capas:

1. **Generación de perfiles de carga** (residencial e industrial) en formato por unidad (pu) para parametrizar cargas controladas externamente (CPL) en Typhoon HIL.
2. **Aplicación de escritorio** (`taller_potencia_app.py`) que controla el RIGOL DL3021 siguiendo esos perfiles en tiempo real, adquiere medidas V/I y las transmite vía TCP/IP al panel SCADA del grupo receptor.
3. **Esquemático HIL** y panel SCADA custom para visualización y validación del sistema.

---

## Estructura del repositorio

```
├── taller_potencia_app.py              # Aplicación principal (GUI Tkinter)
│
├── RIGOL/
│   ├── rigol_dl3021.py                 # Driver VISA para el DL3021
│   ├── curva_vi.py                     # Medición de curva V-I
│   └── pruebas.py                      # Scripts de prueba del instrumento
│
├── Perfiles de carga/
│   ├── load_profile_generator.py       # Generador de perfiles base (residencial/industrial)
│   ├── barrido_fp.py                   # Barrido automático de Factor de Potencia (FP 0→1)
│   ├── completo_residencial_V120.csv   # Perfil residencial completo a 120 V
│   ├── completo_industrial_V120.csv    # Perfil industrial completo a 120 V
│   ├── typhoon_residencial_V120.csv    # Perfil residencial para Typhoon HIL
│   └── typhoon_industrial_V120.csv     # Perfil industrial para Typhoon HIL
│
├── esquematico_final.tse               # Esquemático HIL en Typhoon (circuito principal)
├── scada.cus                           # Panel SCADA personalizado (Typhoon)
├── DG_247_Factory-rel-6de948b-3898934689.epz  # Librería de componentes HIL
│
├── receptor_ethernet_demo.py           # Servidor TCP de prueba (para el grupo SCADA)
├── Protocolo_Ethernet_TallerPotencia.md  # Especificación del protocolo de comunicación
└── project_summary.md                  # Resumen técnico del generador de perfiles
```

---

## Aplicación principal

`taller_potencia_app.py` es una interfaz gráfica (Tkinter) que permite:

- Seleccionar un perfil de carga (tipo residencial/industrial, FP y ciclo).
- Ejecutar el perfil sobre el **RIGOL DL3021** vía USB/VISA, controlando corriente punto a punto.
- Visualizar en tiempo real las curvas de **V**, **I** y **Potencia**.
- Transmitir cada medición al grupo SCADA vía **TCP/IP** (en vivo o en modo post-medición).
- Guardar los datos adquiridos en CSV dentro de `Datos de prueba/`.

### Requisitos

```bash
pip install numpy pandas matplotlib pyvisa
```

> El DL3021 debe estar conectado por USB. El driver VISA de RIGOL (o NI-VISA) debe estar instalado.

### Ejecución

```bash
python taller_potencia_app.py
```

---

## Generación de perfiles de carga

Los perfiles simulan consumo diario interpolando puntos característicos, añadiendo ruido blanco para realismo.

```bash
# Generar un perfil individual
python "Perfiles de carga/load_profile_generator.py"

# Barrido completo de FP (genera 21 casos: FP 0.0 → 1.0 en pasos de 0.05)
$env:PYTHONIOENCODING="utf-8"
python "Perfiles de carga/barrido_fp.py"
```

Los resultados se guardan en `Perfiles de carga/barrido_fp_resultados/FP_X.XX/` con columnas `Time, P, Q` en pu.

**Parámetros clave:**
| Parámetro | Valor |
|---|---|
| Duración total | 720 s (12 min) |
| Resolución temporal | 10 s / muestra |
| P_max residencial | 5 000 W |
| P_max industrial | 50 000 W |
| FP mínimo seguro | 0.001 (evita división por cero) |

---

## Protocolo Ethernet

La app actúa como **cliente TCP**; el SCADA actúa como **servidor TCP**.

| Parámetro | Valor por defecto |
|---|---|
| Protocolo | TCP/IP, IPv4 |
| Puerto | `5025` |
| IP destino | `192.168.1.100` |
| Formato | `t,v,i\n` (ASCII, texto plano) |

Cada paquete es una línea de texto:
```
12.3000,120.123456,0.482301
```
donde `t` es tiempo (s), `v` es voltaje RMS (V) e `i` es corriente RMS (A).

El script `receptor_ethernet_demo.py` sirve como servidor de prueba: recibe paquetes, los guarda en CSV y opcionalmente grafica V e I en vivo.

```bash
python receptor_ethernet_demo.py            # escucha en 0.0.0.0:5025
python receptor_ethernet_demo.py --port 5025 --no-plot
```

Ver `Protocolo_Ethernet_TallerPotencia.md` para la especificación completa.

---

## Simulación HIL (Typhoon)

| Archivo | Descripción |
|---|---|
| `esquematico_final.tse` | Circuito principal del sistema en Typhoon HIL |
| `scada.cus` | Panel SCADA personalizado para monitoreo |
| `DG_247_Factory-rel-6de948b-3898934689.epz` | Librería de componentes del fabricante |

Los perfiles CSV se cargan en Typhoon mediante un bloque **From File** → **Demux** → entradas `P_ref` / `Q_ref` del bloque de carga dinámica (CPL).

---

## Hardware utilizado

- **RIGOL DL3021** — Carga electrónica programable (control vía USB/VISA)
- **Typhoon HIL** — Simulador hardware-in-the-loop
