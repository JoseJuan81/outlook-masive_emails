# Instrucciones para usar script V2

1.- Carga archivo `.csv` con los contactos a los que quieres enviar el correo
2.- Diseña el correo en outlook y envíatelo para asegurar que todo esté ok. El comienzo debe ser: `Hola {name}`
3.- Copia el código fuente del `body` del correo y pégalo en el archivo `html/templates/body.html`
4.- En el archivo anterior ( `body.html` ) Sustituye el valor de la imagen `src` por `"{images[0, 1, 2, ...]}"`
5.- Carga las imágenes a la carpeta `html/images/body`

# Levantar contenedor de Docker
```bash
docker build -t outlook-app .
```
```bash
docker run -it --rm --name running-outlook-app outlook-app
```