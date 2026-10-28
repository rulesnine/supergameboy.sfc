# Fase 3 — Contrato de integración mGBA ↔ Ik Core SGB/ICD2

Estado: **diseño técnico; no integrado, compilado ni validado en NES Mini**.

## Objetivo

Emplear mGBA para CPU/PPU/APU Game Boy y conservar la lógica SGB del runtime Ik Core para comandos SNES (incluido SPC700/DSP). No fusionar dos bucles principales ni ejecutar dos CPU GB simultáneamente. El objetivo de 60 fps y la fidelidad sonora quedan pendientes de medición real.

## Reglas de conservación

- No modificar ni reemplazar el paquete estable #43.
- Aislar la integración en `arquitectura/ikcore-mgba-spc-hibrido`.
- Preservar boot ROM/firmware aportados lícitamente por el usuario y el formato SGBPACK1 existente.
- Probar regresiones por separado en KOF '96 y Castlevania Legends; no extrapolar resultados entre juegos.
- No declarar «60 FPS», «SPC exacto» o «SGB compatible» sin registros de ejecución.

## Límites de subsistemas

1. **GB runtime (mGBA)**: fuente única de CPU, memoria y reloj GB; proporciona estados de PPU y eventos de joypad SGB.
2. **Capturador de protocolo SGB**: reconstruye bits desde líneas P14/P15 en JOYP; entrega paquetes completos con orden temporal y longitud comprobada; no inventa comandos perdidos.
3. **Cola de eventos**: transporta paquetes SGB con `frame_index` y `cycle_index` monotónicos y permite depuración determinista. Si se llena, registrar error; no descartar paquetes silenciosamente.
4. **Ik Core SGB**: consume comandos PAL/ATTR/CHR_TRN/PCT_TRN y SOUND/SOU_TRN únicamente desde el puente. Las transferencias dependientes de VRAM tienen que tomar instantánea del contenido en el instante correcto; no basta con enviar el ID del comando.
5. **SNES audio**: mantiene SPC700/DSP como salida de audio SGB. Definir explícitamente política de mezcla con APU GB y frecuencia de muestreo; no suponer que ambos motores comparten reloj.

## Interfaz propuesta (no es una API ya existente)

```c
typedef struct {
    uint64_t gb_cycles;
    uint64_t gb_frame;
    uint8_t bytes[16];
    uint8_t packet_index;
    uint8_t packet_count;
} IkSgbPacket;

bool ik_sgb_enqueue_packet(const IkSgbPacket *packet);
void ik_sgb_consume_until(uint64_t gb_cycles);
void ik_sgb_notify_vram_transfer(uint8_t command,
                                  const uint8_t *data,
                                  size_t bytes,
                                  uint64_t gb_cycles);
```

La interfaz es **provisional**: adaptar los nombres y estructuras a las firmas reales tras auditar el checkout completo. Los datos de transferencia no deben apuntar a memoria temporal sin una copia con propiedad definida.

## Criterios de aceptación de la primera integración

- El arranque GB llega al mismo punto del programa que la referencia sin pantalla negra.
- Las líneas JOYP reconstruyen exactamente paquetes de 16 bytes y cadenas multipaquete, con contador de descartes en cero.
- ATTR_TRN y PCT_TRN son reproducibles y mantienen marco/atributos.
- SOUND/SOU_TRN llegan en orden y permiten reproducir señales SPC sin cortes introducidos por el puente.
- No se modifican la versión #43 ni sus binarios; toda nueva compilación lleva identificador experimental.
- Registrar `gb_fps`, `host_fps`, tiempo del hilo GB, tiempo SGB y tiempo de audio, además de underruns.
- Comparar dos ejecuciones con los mismos inputs: mismo orden y contenido de paquetes y mismo checksum de transferencia.

## Pruebas mínimas

1. Unit test JOYP: un paquete y secuencia de varios paquetes (orden, bit-packing, reset y timeout).
2. Unit test transferencia: 4096 bytes con checksum conocido y copia estable hasta consumo.
3. Unit test cola: overflow detectable, secuencia temporal estricta y no pérdida silenciosa.
4. Integración visual: arranque, selección de personaje y transición al escenario.
5. Integración audio: muestra de máquina de escribir, voces y cambios de pantalla.
6. Hardware NES Mini: separar tiempos de arranque BIOS, transición y gameplay antes de optimizar.

## Bloqueo actual

El README de esta rama solo documenta la distribución Windows. Antes de escribir un adaptador real hacen falta las rutas y firmas de los fuentes mGBA/Ik Core efectivamente presentes en el checkout. **No sustituir esa auditoría por nombres de funciones supuestos.**
