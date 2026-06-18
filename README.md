# Instrucciones para usar V2

## Variables de entorno
Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

```env
AIRTABLE_TOKEN=tu_token
AIRTABLE_BASE_ID=id_de_la_base
AIRTABLE_CONTACT_TABLE_ID=id_de_la_tabla
AIRTABLE_VIEW="nombre de la vista"   # vista por defecto al ejecutar sin --view

OUTLOOK_SENDER_EMAIL=tu_correo@empresa.com

PREVIEW_EMAIL_BEFORE_SEND=true
PREVIEW_OPEN_IN_BROWSER=true
```

## Flujo de Trabajo

### Opción A — Importar desde archivo EML o MSG (recomendado)

Si no puedes acceder al código fuente del correo en Outlook, guárdalo como
`.eml` o `.msg` en tu carpeta **Descargas** y ejecuta sin argumentos:

```bash
uv run import_email_template.py
```

Tomará automáticamente el archivo `.eml` o `.msg` más reciente de
`C:\Users\domin\Downloads\`. Si el archivo está en otro lugar, pasa la ruta:

```bash
uv run import_email_template.py ruta/al/correo.eml
```

El script:
- Extrae el cuerpo HTML del correo
- Guarda las imágenes inline automáticamente en `html/images/body/` con nombres `a.jpg`, `b.jpg`, etc.
- Reemplaza las referencias de imagen por `{images[0]}`, `{images[1]}`, etc.
- Escribe el resultado en `html/templates/body_html.html`

Después de importar, abre `html/templates/body_html.html` y reemplaza
el nombre del destinatario por `{name}`:

```html
<!-- Antes -->
Hola Juan,
<!-- Después -->
Hola {name},
```

### Opción B — Copiar el código fuente manualmente

1. Diseña el correo en Outlook y envíatelo a ti mismo.
2. Abre el correo recibido y ve a:
   `Más acciones → Ver código fuente`
3. Copia el contenido del `<body>` y pégalo en `html/templates/body_html.html`.
4. Reemplaza el nombre del destinatario por `{name}`.
5. Si tienes imágenes, colócalas en `html/images/body/` con nombres `a.png`, `b.png`, etc.
   y usa `{images[0]}`, `{images[1]}` como valor del atributo `src`.

## Seleccionar vista de Airtable

Al ejecutar `main.py` puedes indicar qué vista de Airtable usar:

```bash
# Usa la vista definida en AIRTABLE_VIEW del .env
uv run main.py

# Usa una vista específica
uv run main.py --view "Lista Contactos Perú :: No Compradores :: correo masivo"
```

## Vista previa del correo

Verifica cómo quedará el correo antes de enviarlo:

```bash
uv run preview.py --name "Juan"
```

El archivo se guarda en `preview/email_preview.html` y se abre automáticamente en el navegador.

## Vista previa del correo

Verifica cómo quedará el correo antes de enviarlo:

```bash
uv run preview.py --name "Juan"
```

El archivo se guarda en `preview/email_preview.html` y se abre automáticamente en el navegador.

## Enviar

El envío usa Outlook Desktop a través de `win32com`, que solo funciona en Windows nativo.
Desde WSL2, usa el Python de Windows directamente:

```bash
/mnt/c/Python313/python.exe main.py --view "Lista Contactos Perú :: No Compradores :: correo masivo"
```

Para enviar a todos los contactos de la vista definida en `.env`:

```bash
./send.sh --subject "Tu asunto aquí"

# Con vista específica y modo prueba
./send.sh --subject "Tu asunto" --view "Lista Contactos Perú :: No Compradores :: correo masivo" --test-email tu@correo.com
```