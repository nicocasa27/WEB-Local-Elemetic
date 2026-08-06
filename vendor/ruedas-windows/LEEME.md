# Las librerías, empaquetadas para Windows

`INSTALAR.bat` las instala desde aquí y **sin tocar internet**:

```bat
pip install --no-index --find-links vendor\ruedas-windows -r requirements.txt tzdata
```

## Por qué están en el repositorio

Porque el taller no tiene internet. Un `pip install` normal se queda esperando
a un servidor al que no va a llegar, y el mensaje que da entonces habla de
tiempos de espera, no de que falte la red. Quien está delante concluye que el
sistema está roto.

Son 19 MB. Es mucho para un repositorio y poco comparado con no poder instalar.

## Qué hay aquí que no está en `requirements.txt`

- **`tzdata`**, que Django sólo declara como dependencia en Windows
  (`sys_platform == "win32"`). Sin él, `TIME_ZONE = "America/Merida"` revienta
  al arrancar con `ZoneInfoNotFoundError`, porque Windows no trae la base de
  zonas horarias que sí traen Linux y macOS. No aparece en `requirements.txt`
  porque ahí no hace falta; aparece aquí porque el destino es Windows.

- **Tres versiones de `psycopg_binary`**: `cp312`, `cp313` y `cp314`. Ese es el
  único paquete compilado, y su rueda sirve para una versión de Python
  exactamente. Con una sola, quien bajara Python de la página oficial —que
  ofrece la más nueva— se encontraría con que la instalación falla diciendo que
  no encuentra el paquete, sin ninguna pista de que el problema es la versión.

## Cómo se rehace, si algún día cambia una versión

Desde una máquina con internet, da igual el sistema operativo:

```bash
rm -rf vendor/ruedas-windows/*.whl
for v in 312 313 314; do
  pip download -r requirements.txt tzdata==2025.3 \
    --dest vendor/ruedas-windows \
    --platform win_amd64 --python-version $v --only-binary=:all:
done
```

`--platform` y `--python-version` son lo que hace que descargue las ruedas de
Windows aunque se corra en otro sistema. Y hay que pedir `tzdata` a mano: pip
evalúa los marcadores de plataforma contra el intérprete que está corriendo,
no contra el de destino, así que la dependencia condicional de Django no se
resuelve sola.
