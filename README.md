# stackfuzz

Un envoltorio de [`ffuf`](https://github.com/ffuf/ffuf) consciente del stack.

`stackfuzz` envía una única petición de reconocimiento a un objetivo web,
identifica su stack tecnológico a partir de la respuesta y luego ejecuta `ffuf`
con **wordlists curadas para ese stack**, en lugar de fuzzear a ciegas con una
lista genérica.

Detecciones soportadas: **Django**, **Next.js**, **NestJS/Express**, **Flask**,
**Laravel**. Puede detectar varias a la vez, en cuyo caso sus wordlists se
combinan (sin duplicados). Si no detecta nada, recurre a `generic.txt`.

## Cómo funciona

1. **Reconocimiento** — un GET con `httpx` a la URL base, recogiendo cabeceras y
   cookies de la respuesta, más unas pocas rutas de sondeo (`/admin/`,
   `/_next/`, `/api/`).
2. **Detección** — reglas de firma sobre cabeceras / nombres de cookies /
   códigos de estado de los sondeos (p. ej. `x-powered-by: Next.js`, una cookie
   `laravel_session`, una cookie `csrftoken`, una cabecera `Server` con
   `Werkzeug`).
3. **Resolución** — cada tecnología detectada se mapea a una o más wordlists
   incluidas; si hay varias, se fusionan en una sola lista deduplicada.
4. **Fuzzing** — se construye y ejecuta `ffuf -u <objetivo>/FUZZ -w <wordlist>`.

## Requisitos

- Python **3.9+**
- [`ffuf`](https://github.com/ffuf/ffuf) instalado y accesible en el `PATH`
  (solo hace falta para fuzzear de verdad — `--dry-run` funciona sin él).

Funciona en Linux, macOS y Windows; no requiere Kali ni ninguna distribución en
particular.

## Instalación

Desde la raíz del proyecto:

```bash
pip install -e .
```

Esto instala el comando `stackfuzz` (mediante el entry point de
`[project.scripts]`) e incluye las wordlists como datos del paquete, de modo que
funciona desde cualquier directorio una vez instalado.

También se puede ejecutar sin instalar:

```bash
python -m stackfuzz https://example.com --dry-run
```

## Uso

```bash
stackfuzz <url-objetivo> [--dry-run] [--timeout SEGUNDOS] [--no-color] [-- <flags extra de ffuf>]
```

- `target` — obligatorio, debe ser una URL `http(s)://` válida.
- `--dry-run` — muestra el comando `ffuf` en lugar de ejecutarlo.
- `--timeout` — tiempo límite HTTP para la petición de detección (por defecto: 10 s).
- `--no-color` — desactiva los colores de la salida.
- `--version` — muestra la versión y termina.
- Todo lo que vaya después de `--` se pasa tal cual a `ffuf` (códigos de
  coincidencia, hilos, filtros, etc.).

### Ejemplos

Detectar y mostrar el comando que se ejecutaría (no hace falta `ffuf`):

```bash
stackfuzz https://example.com --dry-run
```

Detectar y fuzzear, añadiendo flags propios de ffuf:

```bash
stackfuzz https://example.com -- -mc 200,301,302,401,403 -t 40
```

### Salida

```
  stackfuzz v0.1.0

  Objetivo    https://example.com
  Respuesta   200 en 0.42s

[✓] Stack detectado: Next.js
    └─ señal: cabecera «x-powered-by: Next.js»
    └─ señal: ruta /_next/ responde 200
[»] Wordlist: nextjs.txt — 18 rutas

[»] Comando ffuf (simulación, no se ejecuta):

    ffuf -u https://example.com/FUZZ -w .../wordlists/nextjs.txt
```

Cada detección se justifica con la señal concreta que la disparó, para que se
pueda juzgar si es fiable. Las advertencias y los errores se escriben en
`stderr`, así que `stackfuzz ... > salida.txt` guarda solo el resultado. Los
colores se activan solos cuando la salida es una terminal y se desactivan al
redirigir, con `--no-color` o con la variable de entorno `NO_COLOR`.

Códigos de salida: `0` correcto, `1` falta `ffuf`, `2` objetivo inválido.

## Limitación: la detección es aproximada

La detección depende de señales que el servidor *puede* exponer, y en producción
es habitual que estén ocultas:

- `x-powered-by` (la señal más fuerte para Next.js / Express) suele
  **eliminarse en producción**.
- Un proxy inverso o CDN (nginx, Cloudflare, ...) normalmente **sobrescribe o
  elimina la cabecera `Server`**, ocultando pistas de Werkzeug/Gunicorn.
- Las cookies pueden no establecerse en la página inicial, o estar renombradas.

Cuando no encuentra ninguna señal, `stackfuzz` **no adivina**: recurre a
`generic.txt`. Tratá el stack detectado como una pista, no como una certeza; ante
la duda, ejecutá también la lista genérica.

## Wordlists

Este MVP incluye **únicamente sus propias wordlists curadas**
(`stackfuzz/wordlists/`) con rutas realistas por stack. Deliberadamente **no**
incluye ni referencia SecLists ni rutas de wordlists de Kali. Para ampliar la
cobertura, agregá un `.txt` en `stackfuzz/wordlists/` y mapealo en
`TECH_TO_LISTS`, dentro de [`stackfuzz/resolver.py`](stackfuzz/resolver.py).

## Desarrollo

Instalar con las dependencias de desarrollo y ejecutar los tests:

```bash
pip install -e ".[dev]"
pytest
```

Los tests no salen a la red ni necesitan `ffuf`: el reconocimiento se simula con
`httpx.MockTransport` y la ejecución de `ffuf` se sustituye con monkeypatch.

## Estructura del proyecto

```
stackfuzz/
  detector.py   # reconocimiento + reglas de firma -> tecnologías detectadas
  resolver.py   # tecnologías -> wordlists (fusión y deduplicación si hay varias)
  runner.py     # construcción / comprobación / ejecución del comando ffuf
  output.py     # formato de la salida: colores, símbolos y bloques
  cli.py        # entry point basado en argparse
  wordlists/    # wordlists curadas por stack
```

## Aviso legal

Fuzzear lanza cientos de peticiones contra el objetivo. Usá `stackfuzz`
únicamente sobre sistemas propios o sobre los que tengas autorización explícita
por escrito.

## Licencia

Publicado bajo la licencia MIT — ver [LICENSE](LICENSE) para el texto completo.

En resumen: podés usar, modificar y distribuir este código, incluso con fines
comerciales, siempre que conserves el aviso de copyright. El software se
entrega sin garantía de ningún tipo.
