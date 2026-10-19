# Markdown → PDF corporativo

Conversor local en Python: portada con varios logotipos, índice enlazado con números
de página y encabezado/pie en **todas** las páginas, incluida la portada.

## Uso rápido

Requiere Python **3.12 o posterior**. No necesita navegador, LaTeX ni servicios externos.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python md_to_pdf.py examples/api.md -c examples/empresa.json -o output/pdf/api-demo.pdf
```

En este entorno el `.venv` ya está creado con Python 3.12.14 y las dependencias
instaladas. En Windows activalo con `.venv\Scripts\activate`.

Para tu documento:

```sh
python md_to_pdf.py ruta/documentacion.md -c examples/empresa.json
```

Sin `-o`, genera el PDF al lado del Markdown. Si omitís el archivo, pregunta su ruta:

```sh
python md_to_pdf.py
```

No reemplaza un PDF existente salvo que pases `--force`. Nunca sobrescribe el
Markdown ni el JSON de configuración. Las salidas se escriben de forma atómica:
un error de conversión no destruye un PDF anterior.

## Personalización

Copiá [examples/empresa.json](examples/empresa.json) y editá:

| Campo | Uso |
| --- | --- |
| `company`, `title`, `subtitle` | Empresa y textos de portada; título por defecto: nombre del archivo |
| `author`, `version` | Autor y versión en portada |
| `header`, `footer` | Encabezado y pie; el número de página se agrega automáticamente |
| `logos` | Lista de archivos locales PNG/JPEG para la portada |

Los logotipos se resuelven **respecto del JSON**, no del directorio de ejecución.
Las imágenes del Markdown se resuelven respecto del propio `.md`. Los dos logos
de ejemplo son **ficticios**: reemplazalos por los de tu empresa. Usá idealmente
uno o dos logos horizontales; un exceso puede hacer que la portada ocupe más de
una página. Header y footer admiten hasta dos líneas cortas.

## Markdown admitido

- Títulos de niveles 1–6; el índice incluye niveles 1–3.
- Párrafos, negrita, cursiva, código inline, listas y tablas con encabezado repetido.
- Bloques de código (incluido JSON), líneas largas y tablas que continúan en otra página.
- Enlaces HTTP/HTTPS/mailto y anclas internas a títulos (`[Errores](#errores)`).
- Imágenes locales PNG/JPEG con escalado proporcional.
- Acentos y caracteres habituales en español, con fuentes PDF estándar.

### Límites deliberados

No es un motor HTML/CSS ni convierte OpenAPI automáticamente. HTML se muestra
como texto, los bloques de cita no tienen estilo especial y las reglas horizontales
son separación visual. No hay Mermaid, fórmulas, resaltado de sintaxis, SVG,
emoji ni cobertura Unicode universal. Las anclas usan títulos en minúsculas, sin
puntuación y con guiones en lugar de espacios; los duplicados agregan `-1`, `-2`.
Las tablas tienen columnas del mismo ancho: evitá demasiadas columnas.

No descarga imágenes remotas ni abre enlaces al generar: HTTP/HTTPS/mailto sólo
quedan como enlaces clicables. Los esquemas no admitidos se rechazan. Los recursos
locales pueden estar fuera del proyecto: procesá sólo archivos de confianza.

## Desarrollo y verificación

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Las pruebas generan PDFs reales y verifican portada con logos, enlaces y destinos
del índice, encabezado/pie por página, acentos, código/tablas extensos, rutas,
protección ante sobrescritura, recursos remotos y entrada interactiva.

## Por qué Python

ReportLab dibuja directamente el documento, por eso no necesita dependencias
nativas de composición como Pango o un navegador instalado. `markdown-it-py`
interpreta Markdown; ReportLab pagina y recalcula el índice en varias pasadas.

La contrapartida es un subconjunto de Markdown y diseño programado en lugar de
CSS. Si más adelante necesitás maquetación editorial compleja o HTML existente,
conviene evaluar un motor HTML/CSS, con más dependencias de sistema.
