# Configuración de Audio para Traducción en Tiempo Real (macOS)

Para que el script pueda capturar el audio de tu llamada (Meet, Zoom, etc.) y tú puedas seguir escuchándola, necesitamos configurar un dispositivo de "Multi-Salida" en macOS.

## 1. Instalar BlackHole 2ch

Si no lo tienes instalado:
1.  Descarga BlackHole 2ch: [https://existential.audio/blackhole/](https://existential.audio/blackhole/)
2.  Instala el paquete y reinicia Core Audio o tu Mac si es necesario.

## 2. Configuración en "Configuración de Audio MIDI" (Audio MIDI Setup)

1.  Abre la aplicación **Configuración de Audio MIDI** (búscala con Spotlight `Cmd + Space`).
2.  En la esquina inferior izquierda, haz clic en el botón `+`.
3.  Selecciona **Crear dispositivo de salida múltiple** (Create Multi-Output Device).
4.  En el panel de la derecha, verás una lista de dispositivos. Marca las casillas para:
    *   **Tus auriculares/altavoces principales** (ej. "External Headphones" o "MacBook Pro Speakers"). **Importante**: Marca este primero para que sea el dispositivo "Master" (reloj maestro).
    *   **BlackHole 2ch**.
5.  Asegúrate de que la casilla "Corrección de deriva" (Drift Correction) esté marcada para **BlackHole 2ch**.

## 3. Seleccionar la Entrada/Salida en el Sistema

1.  Ve a **Preferencias del Sistema** > **Sonido** > **Salida**.
2.  Selecciona el **Dispositivo de salida múltiple** que acabas de crear.
    *   *Nota: Cuando seleccionas esto, no podrás controlar el volumen con las teclas del teclado. Debes ajustar el volumen antes o usar controles en las aplicaciones.*

## 4. Configuración en la App de Llamadas (Meet, Zoom, etc.)

*   En la configuración de audio de Google Meet o Zoom, asegúrate de que el **Altavoz/Salida** esté configurado en **"Igual que el sistema"** (Same as System) o selecciona explícitamente el **Dispositivo de salida múltiple**.

## 5. Ejecutar el Script

1.  Abre una terminal en la carpeta del proyecto.
2.  Activa el entorno virtual (si no lo has hecho):
    ```bash
    source venv/bin/activate
    ```
3.  Configura tu API Key:
    ```bash
    export GOOGLE_API_KEY="TU_CLAVE_API_AQUI"
    ```
4.  Ejecuta el script:
    ```bash
    python audio_bridge.py
    ```

## ¿Qué acabamos de hacer?

Ahora, cualquier sonido que salga de tu computadora (incluyendo la voz de la otra persona en la llamada):
1.  Sonará en tus auriculares (para que tú escuches).
2.  Sonará en BlackHole (para que nuestro script de Python lo capture).

El script de Python leerá de "BlackHole 2ch" y enviará ese audio a Gemini.
Gemini devolverá la traducción, y el script reproducirá esa traducción directamente en tu "Salida por defecto" (tus auriculares).
