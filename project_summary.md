# Resumen del Proyecto: Generación de Perfiles de Carga para Typhoon HIL

Este documento resume el estado del proyecto de generación de perfiles de carga dinámicos para que cualquier otro asistente de IA o desarrollador pueda continuar el trabajo de forma inmediata.

---

## 1. Objetivo Principal
El objetivo del proyecto es generar perfiles de consumo eléctrico dinámicos (residenciales e industriales) con resolución temporal configurable y en formato por unidad (**pu**) de potencia activa ($P$) y reactiva ($Q$). Estos perfiles están diseñados específicamente para parametrizar cargas dinámicas controladas externamente (**CPL - Controlled Power Load**) en el entorno de simulación **Typhoon HIL**.

Adicionalmente, se requiere realizar un **barrido sistemático del Factor de Potencia (FP)** para estudiar la respuesta del sistema ante diferentes comportamientos de desfase (de inductivo puro/bajo FP a resistivo/FP unitario).

---

## 2. Implementación Actual
Se han implementado dos scripts de Python principales en el directorio del proyecto:

1.  **`load_profile_generator.py`**:
    *   Define las curvas de carga base (residencial e industrial) interpolando puntos característicos típicos de consumo diario.
    *   Añade pequeñas fluctuaciones aleatorias (ruido blanco normal) para dar realismo a la curva.
    *   **Configuración temporal actual**: Ajustado para simular **12 minutos** de tiempo de ejecución total ($720\text{ s}$) con muestras tomadas **cada 10 segundos** (un total de **72 muestras** por perfil).
    *   Calcula $P$, $Q$, $S$, $I$ y $V$ basándose en la parametrización de entrada, pero está preparado para exportar curvas a nivel general.

2.  **`barrido_fp.py`**:
    *   Importa la lógica del generador base y ejecuta un barrido automático de Factores de Potencia (FP) constantes.
    *   **Rango de barrido**: Desde `0.0` hasta `1.0` con un paso de `0.05` (generando 21 casos de FP distintos).
    *   Normaliza las potencias $P$ y $Q$ a por unidad (pu) dividiéndolas por la potencia máxima configurada ($P_{max\_res} = 5000\text{ W}$, $P_{max\_ind} = 50000\text{ W}$).
    *   Exporta los archivos resultantes ordenándolos en subcarpetas para cada FP.

---

## 3. Estructura del Proyecto
El espacio de trabajo se organiza de la siguiente manera:

```text
Perfiles de carga/
│
├── load_profile_generator.py      # Script base con curvas de consumo, ruido y CLI
├── barrido_fp.py                  # Script automatizador del barrido de FP
└── barrido_fp_resultados/         # Carpeta de salida autogenerada
    ├── FP_0.0/
    │   ├── perfil_industrial_FP0.0.csv
    │   └── perfil_residencial_FP0.0.csv
    ├── FP_0.05/
    │   ├── perfil_industrial_FP0.05.csv
    │   └── perfil_residencial_FP0.05.csv
    │   ...
    └── FP_1.0/
        ├── perfil_industrial_FP1.0.csv
        └── perfil_residencial_FP1.0.csv
```

---

## 4. Tecnologías y Librerías Utilizadas
El entorno de ejecución está configurado con:
*   **Python**: Versión 3.13 (instalado en entorno virtual local `.venv`).
*   **Librerías principales**:
    *   `numpy` (manipulación de vectores, ruido aleatorio e interpolaciones).
    *   `matplotlib` (generación de gráficos e inspección visual en `load_profile_generator.py`).
    *   `csv` y `os` (generación de la estructura del proyecto y exportaciones).

---

## 5. Decisiones de Diseño y Especificaciones del CSV
*   **Formato del CSV**: 
    *   **Separador de columnas**: Coma (`,`), estándar internacional.
    *   **Separador de decimales**: Punto (`.`), estándar internacional.
    *   **Columnas**: Únicamente `Time`, `P` y `Q` (en ese orden).
    *   **Valores**: `Time` en segundos absolutos (`0.0, 10.0, 20.0...710.0`). Las potencias `P` y `Q` en formato **pu** (valores entre `0.0` y `1.0`).
*   **Manejo numérico de FP = 0.0**: 
    *   Dado que $S = P / FP$, un factor de potencia de exactamente `0.0` con potencia activa activa generaría una potencia aparente infinita, induciendo divisiones por cero. 
    *   Para evitarlo, la lógica en `barrido_fp.py` acota el FP a un mínimo de `0.001` (`fp_safe = max(fp_val, 0.001)`) permitiendo una simulación inductiva extremadamente alta y matemáticamente estable.

---

## 6. Problemas Conocidos y Soluciones
*   **UnicodeEncodeError en Windows**:
    El script de generación original imprime caracteres UTF-8 en consola (como el checkmark `✓`). En sistemas Windows que usen `cp1252` por defecto, esto causa una excepción de encoding.
    *   *Solución*: Forzar la consola a codificar en UTF-8 mediante la variable de entorno antes de ejecutar:
        ```powershell
        $env:PYTHONIOENCODING="utf-8"
        python barrido_fp.py
        ```

---

## 7. Trabajo Pendiente / Siguientes Pasos
El backend matemático y la generación de datos están al 100%. Lo que resta es la integración de estos datos dentro del entorno gráfico de Typhoon HIL:
1.  **Carga de perfiles en Typhoon HIL**:
    *   Importar los archivos CSV autogenerados en el bloque **From File** (dentro de *Signal Processing > Sources*).
    *   Separar las salidas mediante un bloque **Demux** de dos salidas (donde la señal 1 es $P_{pu}$ y la señal 2 es $Q_{pu}$).
2.  **Configuración del Bloque Load**:
    *   Usar un componente de carga dinámica (ej: *Constant Power Load* o *Three-Phase Dynamic Load*).
    *   Configurar el modo de control de la carga como **External** o *Signal Processor*.
    *   Conectar las señales de salida del Demux a los puertos `P_ref` y `Q_ref` de la carga para completar el lazo de simulación.
