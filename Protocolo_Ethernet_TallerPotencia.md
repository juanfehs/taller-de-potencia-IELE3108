# Protocolo de transmisión Ethernet — Taller de Potencia

**Grupo emisor:** Juan Felipe — Taller de Potencia, IELE, Uniandes
**Destino:** Grupo SCADA / HMI
**Sentido:** unidireccional (mi app → SCADA)

Este documento describe el protocolo Ethernet que usa mi aplicación para enviar
las medidas del DL3000 hacia su HMI. SCADA solo necesita escuchar el puerto TCP
acordado y parsear el flujo de texto que llega.

---

## 1. Capa de transporte

| Parámetro            | Valor                                              |
|----------------------|----------------------------------------------------|
| Protocolo            | TCP/IP, IPv4                                       |
| Codificación         | ASCII / UTF-8 (texto plano, sin cabecera binaria)  |
| Rol de mi app        | **Cliente** TCP (hace `connect`)                   |
| Rol de SCADA         | **Servidor** TCP (hace `bind` + `listen` + `accept`) |
| Puerto por defecto   | `5025` (configurable en mi app)                    |
| IP destino por defecto | `192.168.1.100` (configurable en mi app)         |

> **Importante:** SCADA debe levantar el servidor **antes** de que yo presione
> "Enviar a DL3000" en mi app. Si mi app no logra conectarse hace `connect` con
> timeout de 5 s y muestra error; tendría que reintentar.

---

## 2. Formato del paquete

Cada medida del DL3000 se envía como **una línea de texto** terminada en `\n`:

```
t,v,i\n
```

| Campo | Tipo  | Unidad   | Formato         | Ejemplo     |
|-------|-------|----------|-----------------|-------------|
| `t`   | float | segundos | `%.4f`          | `12.3000`   |
| `v`   | float | volts    | `%.6f`          | `120.123456`|
| `i`   | float | amperes  | `%.6f`          | `0.482301`  |

Separador entre campos: coma (`,`). Separador entre registros: salto de línea
(`\n`, byte `0x0A`).

### Ejemplo de flujo recibido

```
0.0000,120.123456,0.139000
10.0000,120.118912,0.124400
20.0000,120.121845,0.127800
30.0000,120.114207,0.130300
...
710.0000,120.117500,0.118500
```

- `t` corresponde a la columna `Time` del perfil de carga (de 0 a 710 s con
  paso de 10 s en los perfiles actuales).
- `v` es el voltaje RMS medido por el DL3000 (V).
- `i` es la corriente RMS medida por el DL3000 (A).
- La potencia activa instantánea se puede calcular como `P = v * i` (W).

---

## 3. Modos de envío

Mi app soporta dos modos, seleccionables desde la barra superior:

### 3.1 Envío en vivo (`Ethernet en vivo` activado)

- Se abre un único socket TCP al inicio del ciclo.
- Cada punto del perfil se envía **inmediatamente después** de medir V y I.
- El periodo entre paquetes lo dicta la columna `Time` del perfil y el factor
  de velocidad de mi app (default 1× → 10 s entre paquetes para los perfiles
  actuales).
- El socket se cierra al terminar el ciclo (o al detener manualmente).

### 3.2 Envío post-medición (`Enviar Ethernet (post)`)

- Se ejecuta al final, después de completar la medición.
- Envía los puntos del último ciclo en ráfaga (sin pausas) por un socket nuevo.
- Útil para hacer "replay" si SCADA no estaba escuchando durante la prueba en
  vivo.

En ambos modos el formato del paquete es idéntico.

---

## 4. Identificación de mi grupo

El protocolo actual **no incluye un campo de ID de grupo** dentro del payload.
SCADA puede distinguir grupos de dos formas:

1. **Por dirección IP de origen**: cada vez que SCADA acepta una conexión
   (`server.accept()`), recibe la tupla `(ip, puerto)` del cliente. Esa IP
   identifica el grupo.
2. **Por puerto destino**: si asignan un puerto distinto a cada grupo, mi app
   se configura para apuntar a ese puerto.

Si necesitan que el ID vaya **dentro del paquete**, avísenme y agrego un
prefijo en cada línea (por ejemplo `G3,12.0,120.123,0.482`).

---

## 5. Código de envío (referencia)

Este es el fragmento que mi app usa internamente. **No necesitan ejecutarlo**;
es solo para que vean qué se está mandando exactamente.

```python
import socket

# Mi app abre el socket cliente:
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(("192.168.1.100", 5025))   # IP y puerto de SCADA

# Por cada medida del DL3000:
t, v_med, i_med = 12.0, 120.123456, 0.482301
pkt = f"{t:.4f},{v_med:.6f},{i_med:.6f}\n"
s.sendall(pkt.encode())

# Al final del ciclo:
s.close()
```

---

## 6. Receptor de prueba (Python)

Anexo el script `receptor_ethernet_demo.py` que pueden usar como base o como
herramienta de verificación. Levanta un servidor TCP, imprime cada paquete
recibido, lo guarda a CSV y opcionalmente grafica V e I en vivo con matplotlib.

```bash
# Uso básico (escucha en 0.0.0.0:5025)
python receptor_ethernet_demo.py

# Cambiar puerto o desactivar gráfica
python receptor_ethernet_demo.py --port 5025 --no-plot
```

---

## 7. Resumen para coordinar

Para arrancar las pruebas necesitamos confirmar entre los dos grupos:

| Parámetro                               | Valor que ustedes definen   |
|-----------------------------------------|-----------------------------|
| IP del servidor SCADA en la red de lab  | _____________________       |
| Puerto TCP en el que escucharán         | _____________________       |
| ¿Necesitan ID de grupo en cada paquete? | sí / no                     |
| ¿Confirman formato `t,v,i\n` ASCII?     | sí / requieren cambio       |

Cuando me pasen IP y puerto los configuro en mi app y hacemos una prueba en
vivo.
