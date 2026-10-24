# La Mañana

Genera al ejecutarla un periódico de noticias nacionales de Chile en **un PDF de una sola página**. La versión alfa funciona **sin GUI**, con News y **Ollama en Docker**, y lee sus preferencias de `config.json` en cada ejecución. La interfaz de escritorio anterior sigue disponible como alternativa local.

## Alfa: generar en el Dell con Docker

Requiere Docker Engine y Docker Compose funcionando y accesibles para tu usuario, además de internet para la primera instalación, descargar el modelo y consultar los medios. No requiere Python ni un escritorio instalados en el Dell: Python, Cairo y las fuentes tipográficas van dentro de la imagen de News.

Desde la carpeta del proyecto, ejecuta:

```bash
./generar.sh
```

El script también se puede invocar mediante su ruta absoluta desde otra carpeta. Realiza lo siguiente:

1. Inicia el contenedor de Ollama y espera a que responda.
2. Construye la imagen de News, reutilizando las capas que ya existen.
3. Lee `config.json` y comprueba el modelo. Si falta y `auto_pull_model` es `true`, lo descarga en Ollama. La primera descarga de Qwen3 4B ocupa unos 2,5 GB; las siguientes ejecuciones reutilizan el volumen `ollama_models`.
4. Descarga las noticias, selecciona **7** de las últimas **24 horas** y genera **un PDF de una página Carta** en `output/`.
5. El contenedor de News termina y devuelve un código de salida: `0` si terminó correctamente o un valor distinto si falló. Ollama permanece disponible y libera el modelo de RAM según `keep_alive`.

La configuración inicial **no abre ventanas ni visores, no imprime, no guarda PNG ni JSON auxiliares y no instala cron**. Si no hay siete noticias válidas, o no se puede completar una edición fiel al formato, el programa informa el error y no publica una edición con menos noticias.

## Configuración de la alfa

Edita **`config.json`**. Los cambios se leen en la próxima ejecución, sin reconstruir la imagen por cambiar preferencias. `config.example.json` es una copia inicial de referencia; si falta el archivo principal, cópialo:

```bash
cp config.example.json config.json
```

Si conservas un `config.json` de la versión de escritorio, actualiza su proveedor, URL, modelo y opciones para Ollama usando el ejemplo como referencia y conservando tus fuentes y temas. La ejecución por consola exige `provider` explícito para evitar conectarse silenciosamente a LM Studio. En Compose la URL es `http://ollama:11434`; `localhost` dentro del contenedor de News apunta al propio contenedor.

Los campos principales son:

| Campo | Valor inicial / función |
| --- | --- |
| `provider` | `ollama`; conserva `lmstudio` para configuraciones anteriores |
| `base_url` | `http://ollama:11434`, la dirección interna del servicio de Compose, sin `/api` ni `/v1` |
| `model` | `qwen3:4b`; puedes cambiarlo, por ejemplo, a `qwen3:1.7b` |
| `model_options` | Parámetros nativos de Ollama: contexto, hilos, GPU, temperatura, top-p, top-k, min-p, penalización de repetición y semilla; admite opciones adicionales de Ollama |
| `think` | `false`: desactiva el razonamiento en los modelos que admiten ese control |
| `keep_alive` | `10m`: tiempo que el modelo permanece en RAM después de una petición |
| `auto_pull_model` | `true`: descarga el modelo configurado si todavía no existe |
| `structured_output` | `true`: exige al modelo respuestas mediante el esquema JSON de cada operación |
| `system_prompt` | Instrucciones editoriales para el modelo, editables |
| `paper`, `article_count`, `lookback_hours` | `Carta`, `7`, `24` |
| `candidates_per_source`, `technology_candidates_per_source` | Máximo de candidatos aceptados por fuente general y tecnológica: `8` y `4` |
| `timeout_seconds` | `1800`: espera máxima por petición a Ollama, incluida la descarga inicial |
| `connect_timeout_seconds`, `download_timeout_seconds` | Espera de conexión y de lectura de los medios: `5` y `25` segundos |
| `max_download_bytes` | Máximo descargado por documento: `4000000` bytes |
| `user_agent`, `accept_language` | Cabeceras usadas al consultar los medios |
| `max_output_tokens`, `max_retry_output_tokens` | `1024` inicialmente y hasta `2048` en un reintento si se trunca el JSON. No dupliques estos límites en `model_options.num_predict` |
| `max_article_chars` | `8000`: texto máximo de cada artículo enviado al modelo |
| `output_dir` | `./output`; también puedes elegir una subcarpeta, como `./output/diario`, dentro del directorio montado |
| `open_pdf_after_generation` | `false` |
| `print_after_generation`, `printer` | Impresión desactivada. Se conserva el nombre de impresora; la conexión de CUPS desde Docker queda para una futura versión |
| `save_preview`, `save_metadata` | `false`; puedes activar PNG y JSON auxiliares para revisar resultados |
| `sources` | Fuentes completas: nombre, URL de portada, RSS, ruta de artículos, tema y filtros |
| `topics` | Catálogo editable de temas |

`model_options.num_ctx` comienza en `16384`, `num_thread` en `2` y `num_gpu` en `0`, para probar el i5 de dos núcleos del Dell por CPU. La memoria permite probar el modelo, pero el tiempo de una edición y la calidad de los resúmenes deben medirse allí con noticias reales. El programa nunca sustituye silenciosamente el modelo elegido.

En cada fuente puedes modificar `name`, `page_url`, `article_prefix`, `feed_url`, `section`, `require_chile`, `enabled`, `require_date_in_url` y `allow_external_feed_articles`. Para una fuente nueva con URLs sin fecha, usa `require_date_in_url: false`; para un RSS que enlace a otros dominios, `allow_external_feed_articles: true`. `enabled: false` la conserva sin consultarla. Una sección vacía usa el tema Nacionales. Se mantienen los filtros de fecha y texto suficiente.

Las rutas relativas de `output_dir` se resuelven desde la carpeta del archivo JSON. En Docker, la carpeta `output/` del proyecto está montada en `/app/output`. El JSON se monta para lectura y los modelos se guardan en un volumen independiente de la imagen de la aplicación. Ollama se comunica con News por la red de Compose y no publica un puerto en el Dell.

Para comprobar la configuración o generar una maqueta, sin iniciar Ollama ni descargar modelos:

```bash
mkdir -p output
docker compose build news
docker compose run --rm --no-deps -T news --check-config
docker compose run --rm --no-deps -T news --demo
```

La maqueta queda marcada como tal; no contiene noticias reales. Para consultar el servicio:

```bash
docker compose ps
docker compose logs ollama
```

Para validar sin Docker, si ya tienes las dependencias Python locales, usa `./generar-local.sh --check-config`. Para desarrollo, `python3 -m unittest discover -s tests -v` comprueba también la API nativa de Ollama simulada y el flujo alfa de siete noticias a un único PDF Carta, sin visor ni impresión. No ejecuta un modelo real.

## Interfaz de escritorio y LM Studio (alternativa local)

Las secciones siguientes describen la interfaz anterior. Para usarla, configura `provider: "lmstudio"`, `base_url: "http://localhost:1234/v1"`, el identificador de tu modelo y activa `save_preview` para la vista previa. En `model_options`, usa los parámetros admitidos por LM Studio, por ejemplo `{"temperature": 1.0, "top_p": 0.95, "top_k": 64}`. Ejecuta `./abrir-app.sh`. Los comandos locales usan `./generar-local.sh`; `./generar.sh` está reservado para la alfa dockerizada.

La edición reserva **al menos una noticia de Tecnología** cuando hay artículos recientes relacionados con Chile. Esa nota forma parte del total: si eliges siete, se incluyen siete en total, con tecnología entre ellas. Se buscan temas como inteligencia artificial, ciberseguridad, software, conectividad e innovación. Si no se encuentran artículos de tecnología en el período elegido, se indica en los avisos y se puede ampliar la ventana de noticias.

## Ejecutar

1. En LM Studio, carga tu modelo **Gemma 4 it / Instruct** y activa **Developer → Start Server**. La URL habitual es `http://localhost:1234/v1`.
2. Abre la app desde esta carpeta:

   ```bash
   ./abrir-app.sh
   ```

3. En **Modelo local**, pulsa **Detectar** y elige tu modelo. En **Edición**, personaliza las opciones y haz clic en **Generar mi periódico**. El papel predeterminado es **Carta (Letter)**; también puedes elegir A4, el período de noticias y la carpeta de salida.

La interfaz da prioridad al periódico, con un panel de configuración compacto, tarjetas claras y controles redondeados. La cabecera muestra la última comprobación de conexión con LM Studio y el panel **Actividad** informa del progreso. Las ventanas de fuentes, temas e impresión comparten el mismo estilo.

En la vista previa, usa la **rueda del mouse** para acercar o alejar el periódico, centrando el zoom donde está el puntero. Mantén pulsado el botón izquierdo y **arrastra** para recorrer la hoja ampliada. Pulsa **Ajustar página** o haz **doble clic** para volver a ver la página completa.

## Elegir y añadir fuentes

En la pestaña **Edición**, pulsa **Fuentes**. El número del botón indica cuántas secciones están activas.

1. Marca la columna **Usar** para activar o desactivar una fuente. También puedes seleccionar una fila y pulsar **Activar / desactivar** o la barra espaciadora.
2. Pulsa **Añadir…**, escribe el nombre del medio, pega una **URL de sección o RSS/Atom** y elige un tema o escribe uno nuevo.
3. Pulsa **Guardar fuente** y luego **Guardar fuentes** para aplicar la selección.

Puedes editar o eliminar entradas. **Restaurar fuentes iniciales** recupera y activa los medios incluidos, conservando las fuentes nuevas. **Cancelar** cierra el gestor sin aplicar sus cambios. Las preferencias se guardan en `config.json` y se usan tanto en la app como al generar desde la terminal.

Las fuentes nuevas se filtran por relación con Chile, fecha y texto suficiente. Se admite que los artículos tengan URLs sin fecha, y que un RSS alojado en otro dominio enlace al sitio del medio. La lectura funciona con RSS/Atom y páginas que entregan el texto en su HTML o metadatos; un sitio que solo lo carga con JavaScript, exige iniciar sesión o bloquea las descargas puede requerir un lector específico. Las secciones de noticias nacionales y tecnología de un mismo medio se pueden activar por separado.

## Crear y modificar temas

En **Fuentes → Temas…** puedes **añadir, renombrar y eliminar** categorías. La lista inicial incluye Ciencia, Cultura, Deportes, Economía, Educación, Medioambiente, Nacionales, Política, Regiones, Salud, Seguridad, Sociedad y Tecnología. Los nombres admiten hasta 40 caracteres y se guardan en `config.json`.

Renombrar un tema actualiza todas sus fuentes, incluidas las desactivadas. Para eliminar uno que tenga fuentes, elige primero otro tema en **Al eliminar, reasignar las fuentes a**. Pulsa **Guardar temas** y después **Guardar fuentes** para aplicar los cambios. Cancelar conserva la configuración anterior.

También puedes crear un tema escribiéndolo directamente en el campo **Tema** al añadir o editar una fuente. Asigna cada tema a una sección o RSS que publique ese contenido. El modelo conserva las categorías asignadas; en las fuentes de **Nacionales** clasifica cada artículo entre los temas configurados. Las etiquetas y la cabecera del PDF reflejan los temas de las noticias incluidas.

Las listas de fuentes, temas, modelos, impresoras y tamaños de papel se muestran de **A a Z**, considerando tildes y ñ. El orden se mantiene al añadir o renombrar entradas. Las cantidades y horas siguen un orden numérico ascendente, y las noticias del periódico se presentan por importancia editorial.

## Imprimir

Pulsa **Imprimir…**, selecciona la impresora y confirma con **Imprimir en negro**. Se envía **una copia, por una cara, en Carta (Letter) y blanco y negro** con los valores predeterminados. El diálogo permite cambiar a A4. La app recuerda la impresora elegida y recupera la última edición guardada al abrirse, por lo que puedes imprimirla sin volver a consultar noticias ni usar el modelo.

La impresión utiliza CUPS y sus herramientas `lp`, `lpstat` y `lpoptions`. La app solicita el modo monocromo y, cuando el controlador anuncia una opción de escala de grises, también la aplica. Cada trabajo incluye una sola página, sin portada adicional, y se ajusta al área imprimible. La confirmación muestra que el trabajo se envió a la cola de CUPS y su identificador; el estado físico depende de la impresora.

Para imprimir desde la terminal:

```bash
./generar-local.sh --printers
./generar-local.sh --print-file output/tu-edicion.pdf --printer NOMBRE_IMPRESORA
```

Para generar e imprimir una edición en la misma ejecución:

```bash
./generar-local.sh --print --no-open
```

La impresión ocurre al pulsar el botón correspondiente o al indicar `--print` / `--print-file`. El PDF usa texto negro y grises neutros.

Para generar directamente desde la terminal y abrir el PDF:

```bash
./generar-local.sh --open
```

Se usa automáticamente el único modelo Gemma disponible, o el único modelo de texto si no hay Gemma. Si hay varios, elige uno en la app o indica su identificador:

```bash
./generar-local.sh --models
./generar-local.sh --model 'identificador-que-muestra-lm-studio'
```

La interfaz guarda las preferencias en `config.json`. También puedes copiar `config.example.json` a `config.json` y editarlo. Los argumentos del comando tienen prioridad para esa ejecución:

```bash
./generar-local.sh --paper Carta --count 5 --hours 48 --no-open
./generar-local.sh --base-url http://localhost:1234/v1 --output-dir ./output
```

## Requisitos

- Python 3.11 o posterior, Tkinter, Cairo y las dependencias de `requirements.txt`.
- LM Studio con su servidor activo y un modelo de texto cargado.
- Internet para descargar los medios. La inferencia se realiza en el servidor de LM Studio configurado.

Las dependencias ya estaban disponibles en el equipo donde se preparó esta app. Si el lanzador indica que faltan, usa un entorno virtual:

```bash
./instalar.sh
```

Tkinter pertenece a la instalación de Python. La instalación de `pycairo` puede requerir las bibliotecas de desarrollo de Cairo y `pkg-config`; consulta su [guía oficial](https://pycairo.readthedocs.io/en/latest/getting_started.html). El script no instala paquetes del sistema ni pide privilegios administrativos.

Si activaste autenticación en el servidor de LM Studio, configura `LMSTUDIO_API_KEY` en tu entorno. No hace falta una clave de OpenAI ni se utiliza su servicio.

## Gemma y los resúmenes

Gemma 4 puede procesar texto y seguir instrucciones. Usa una variante **it / Instruct**; el tamaño y la cuantización adecuados dependen de la memoria de tu equipo. La app funciona con los modelos de texto que exponga el servidor y no descarga modelos.

Para comenzar, configura en LM Studio un contexto de **16K tokens**, si tu memoria lo permite. La app solicita respuestas sin Thinking mediante `reasoning_effort: "none"`. Si tu versión del servidor rechaza ese parámetro, usa la preferencia de LM Studio: desactiva **Enable Thinking** en los ajustes del modelo. La efectividad del control por API depende del modelo y del runtime; la app no modifica sus ajustes globales.

Cada petición dispone inicialmente de **4096 tokens de salida**, configurables con `max_output_tokens` en `config.json` o con `--max-output-tokens`. Si el servidor corta una respuesta sin completar el JSON, se reintenta una vez con el doble de presupuesto, hasta **8192 tokens**. Un JSON completo sigue pasando las comprobaciones habituales. Si vuelve a agotarse la salida, el error muestra el presupuesto y los tokens de razonamiento cuando el servidor los informa. No se repiten indefinidamente las peticiones truncadas.

Cada artículo se resume por separado. Si recibes errores de contexto, reduce `candidates_per_source` o `max_article_chars`. Los parámetros de muestreo siguen la configuración documentada para Gemma 4: temperatura 1.0, top-p 0.95 y top-k 64.

## Preparación de la edición

1. Consulta únicamente las fuentes activas. De inicio incluye el RSS nacional de Cooperativa y las portadas nacionales de BioBioChile y El Mostrador. Si falla el RSS de Cooperativa, intenta su portada nacional. También incluye [PC e Internet de BioBioChile](https://www.biobiochile.cl/lista/categorias/pc-e-internet) y [Agenda Innovación de El Mostrador](https://www.elmostrador.cl/agenda-pais/agenda-innovacion/). Las URLs añadidas por el usuario se leen como RSS/Atom o como páginas de enlaces según su contenido.
2. Acepta artículos con fecha dentro del período solicitado y al menos 80 palabras de texto accesible. En las fuentes de tecnología exige además señales de relación con Chile en el artículo y vocabulario tecnológico. Descarta textos insuficientes, notas antiguas y duplicados de título. No se eluden bloqueos ni suscripciones.
3. Envía al modelo hasta ocho candidatos por portada nacional y cuatro por sección tecnológica, con titular y extracto, para seleccionar exactamente la cantidad elegida. Pide variedad y un solo artículo por acontecimiento. Cuando hay candidatos de tecnología, garantiza al menos uno dentro del total, aunque el modelo ignore la instrucción de reservarlo. Si el modelo devuelve una cantidad distinta, se le pide corregirla. Si no hay suficientes artículos utilizables, la app lo indica y pide ampliar el período o elegir menos noticias. Es una selección editorial automatizada, no un ranking objetivo de todas las noticias del país.
4. Resume cada artículo seleccionado. El modelo recibe hasta 8.000 caracteres por nota, instrucciones para conservar atribuciones e incertidumbres y un esquema JSON. Las extensiones pedidas son objetivos editoriales: se acepta un resumen sustancial algo más breve y un pequeño margen adicional en palabras y titular. Se comprueba la estructura y que las cifras escritas con dígitos aparezcan en el texto suministrado. Si hace falta corregir algo, se envía el borrador real con sus medidas y el motivo del rechazo; si vuelve a fallar, la generación se detiene. No se rellenan los textos ni se recortan frases automáticamente para alcanzar una cifra exacta de palabras.
5. Mide la maqueta completa antes de exportar. Ajusta cabecera, columnas y espaciados para incluir todas las noticias, con texto principal de al menos 9,8 puntos. Para seis o siete noticias pide resúmenes más breves desde el principio. Si aún no caben, vuelve a resumir todas las notas con una extensión menor; nunca elimina noticias por espacio. Si tampoco cabe esa edición, muestra un error en lugar de guardar una cantidad diferente de la elegida. Se pueden elegir entre tres y siete noticias, en A4 o Carta.

Las comprobaciones de cifras y formato no garantizan fidelidad factual completa. Cada nota incluye su medio, fecha y enlace para contrastarla. Se pide al modelo trabajar únicamente con los artículos descargados; no se le pide recordar noticias actuales.

Los resultados se guardan en `output/` con fecha y hora:

- `.pdf`: periódico con texto seleccionable y enlaces a las fuentes.
- `.png`: vista previa de la página.
- `.json`: temas configurados, fuentes activas, artículos utilizados, textos descargados, resúmenes, modelo, cantidad solicitada e incluida y avisos de lectura. No contiene claves de API.

Se generan PDFs bajo demanda. La app no instala tareas programadas.

## Ver el diseño sin conectar LM Studio

```bash
./generar-local.sh --demo
```

Genera `output/ejemplo.pdf`, claramente marcado como **maqueta** y con textos explicativos en lugar de noticias reales.

## Validación

```bash
python3 -m unittest discover -s tests -v
```

Las pruebas cubren filtros de país y fecha, extracción de artículos, errores de la API local, respuestas JSON inválidas, cifras añadidas y el flujo completo de generación con fuentes y respuestas de modelo simuladas. Se verifican las opciones de impresión Carta, blanco y negro, una copia y ausencia de portadas con CUPS simulado; las pruebas no envían trabajos reales. También se comprueba el PDF con `pdfinfo` y `qpdf` cuando están disponibles. Las pruebas no requieren LM Studio ni acceso a internet.

La vista previa se prueba con imágenes reales y un lienzo simulado: zoom bajo el puntero, límites de desplazamiento, vuelta a página completa, colores y agrupación de eventos antes de dibujar. El visor reutiliza la imagen de Tk durante el zoom y el arrastre, limita su tamaño al área visible y omite cuadros que no han cambiado. La interacción usa cuadros rápidos y afina la imagen tras 150 ms sin movimiento. También se comprueba que cargar otra edición sustituya los píxeles anteriores. Estas pruebas no necesitan abrir una ventana; la latencia final de pantalla requiere comprobarse en una sesión gráfica.

También se comprueba la compatibilidad con configuraciones anteriores, la persistencia de las fuentes elegidas, las fuentes desactivadas, los RSS/Atom externos, los artículos sin fecha en la URL y la conservación de los filtros de Chile, tecnología y actualidad al usar medios nuevos.

Las pruebas de temas verifican persistencia, nombres duplicados, renombrado y reasignación de fuentes, categorías permitidas en la API del modelo, conservación de la cantidad de noticias y etiquetas largas en PDFs de una página.

La prueba con noticias reales y tu modelo requiere ejecutar la app en un entorno con acceso al servidor local y a los medios. En el entorno de desarrollo restringido no fue posible alcanzar `localhost:1234` ni resolver los dominios de noticias.

## Referencias

- [Gemma 4: ficha oficial y configuración](https://ai.google.dev/gemma/docs/core/model_card_4)
- [API compatible de LM Studio](https://lmstudio.ai/docs/developer/openai-compat)
- [JSON estructurado en LM Studio](https://lmstudio.ai/docs/developer/openai-compat/structured-output)
