# Instrucciones para usar V2

## Variables de entorno
1. Crea un archivo `.env` en la raiz de `V2`
2. Crea las siguientes dos variables:
```javascript
    NOTION_TOKEN=token_de_notion_para_conexión
    NOTION_CONTACT_DB_ID=id_de_la_base_de_datos
```

## Flujo de Trabajo
1. Diseña el correo en outlook que quieres enviar a tus contactos.
    Toma en cuenta que `{name}` es la variable que tendrá el nombre de la persona objetivo o quien recibirá el correo.
    Ejemplo: `Hola {name}, este correo te lo envió ...`
    - Puedes agregar emoticones e imágenes si quieres.

2. Envíate el correo a ti mismo para luego acceder al código fuente:

    `Más acciones de desplazamiento/otras acciones/ver código fuente`
3. Copia el `body` del correo y pégalo en el archivo `html/templates/body.html`
4. Si tu correo tiene imágenes entonces debes agregar las siguientes variables en el atributo `src` `"{images[0]}"`
5. `images` es una arreglo que se forma automáticamente cuando agregas las imágenes en la carpeta `html/images/body`
6. Para controlar el orden de aparición de las imágenes te recomiendo que tengan como nombre las letras del abecedario: `a.png, b.png`
7. Define los filtros que quieras aplicar a los contactos bajo el siguiente esquema:

    <code>
        filters = [
            ( column_name_a, [column_value_1, column_value_2])
            ( column_name_b, [column_value_4, column_value_5])
        ]
    </code>

8. Agrega los filtros a la función `.get_contacts(test=False, filter_columns=filters)`
9. Define el "Asunto" del correo