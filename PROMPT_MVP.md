# Prompt para generar el MVP local LiDAR ferroviario

Quiero que generes una primera version local de una herramienta MVP para validar una captura LiDAR ferroviaria a partir de un archivo `.laz`.

## Contexto del proyecto

Estamos preparando una demo de hackathon sobre drones embarcados en una bateadora ferroviaria. La idea es que varios drones realicen pasadas sobre un tramo corto de via con talud para comprobar si un trabajo LiDAR se ha capturado correctamente.

El sistema debe funcionar como un gemelo digital local: carga una nube de puntos LiDAR, visualiza el terreno, calcula metricas basicas de calidad y simula varias pasadas de dron para explicar como se detectarian huecos, sombras, baja densidad o zonas que habria que repetir.

Archivo de prueba disponible:

- `PNOA_2020_AND-C_364-4210_ORT-CLA-RGB.laz`

## Objetivo del MVP

Crear una herramienta local sencilla que permita:

- Cargar un archivo `.laz` de nube de puntos LiDAR.
- Leer coordenadas X, Y, Z y, si existen, colores RGB o clasificaciones.
- Mostrar una vista 3D simple de la nube de puntos.
- Permitir analizar una zona pequena, idealmente un tramo de unos 20 metros de via con su entorno inmediato.
- Calcular metricas basicas de calidad.
- Simular varias pasadas de dron sobre la escena.
- Mostrar un resultado QA con semaforo: verde, amarillo o rojo.

## Funcionalidades minimas

La primera version debe incluir:

1. Carga del archivo `.laz`.
2. Muestreo de puntos si el archivo es demasiado grande para visualizarlo completo.
3. Calculo de metricas:
   - numero total de puntos,
   - bounding box,
   - rango de cotas Z,
   - superficie aproximada,
   - densidad media de puntos por metro cuadrado,
   - cobertura por rejilla.
4. Visualizacion 3D:
   - nube de puntos,
   - eje o corredor simulado,
   - trayectorias de drones,
   - celdas QA o mapa de cobertura.
5. Simulacion de pasadas:
   - pasada 1: reconocimiento general,
   - pasada 2: refuerzo lateral derecho,
   - pasada 3: refuerzo lateral izquierdo o zona de sombra,
   - pasada 4 opcional: pasada adaptativa sobre zonas marcadas en rojo.
6. Resultado QA:
   - verde: cobertura suficiente,
   - amarillo: cobertura irregular,
   - rojo: huecos o baja densidad.

## Enfoque tecnico recomendado

Usa Python para procesar el `.laz` y una visualizacion web sencilla para la demo.

Tecnologias sugeridas:

- Python 3.12
- laspy
- lazrs
- numpy
- pandas opcional
- Flask o FastAPI para servir datos locales
- Three.js para visualizar la escena 3D

Tambien se puede usar Plotly si se necesita una version mas rapida, pero la demo ideal debe usar Three.js porque queremos una animacion visual de drones y gemelo digital.

## Interfaz esperada

Crear una interfaz local con:

- panel izquierdo: carga/seleccion del archivo y parametros,
- visor central: nube LiDAR, terreno y pasadas de drones,
- panel derecho: metricas, estado QA y leyenda de colores.

Controles minimos:

- boton para cargar o analizar el archivo de ejemplo,
- selector de numero de pasadas,
- selector de tamano de rejilla,
- boton para iniciar animacion de drones,
- boton para mostrar mapa QA.

## Logica QA simplificada

Dividir la zona analizada en una rejilla 2D usando X/Y.

Para cada celda calcular:

- numero de puntos,
- densidad aproximada,
- cota minima,
- cota maxima,
- rango Z,
- si la celda esta suficientemente cubierta.

Clasificacion sugerida:

- Verde: densidad suficiente y sin huecos importantes.
- Amarillo: densidad media o cobertura irregular.
- Rojo: celda vacia, baja densidad o posible sombra/oclusion.

No hace falta implementar IA real en esta primera version. Se puede presentar como una primera capa heuristica que luego evolucionara a IA para segmentacion, deteccion de anomalias y comparacion entre campanas.

## Simulacion de drones

La simulacion no tiene que ser fisicamente perfecta. Debe servir para explicar el flujo operacional:

- La bateadora avanza por la via.
- Los drones despegan o se posicionan alrededor del tramo.
- Cada pasada observa el terreno desde un angulo distinto.
- El sistema fusiona las observaciones.
- Las zonas sin cobertura suficiente quedan marcadas para repetir captura.

Representar las pasadas con lineas animadas, puntos luminosos o modelos simples de dron.

## Entregables esperados

Genera una estructura sencilla con:

- `README.md` con instalacion, uso y explicacion del MVP.
- `requirements.txt` para Python.
- script de analisis LiDAR, por ejemplo `src/process_laz.py`.
- servidor local, por ejemplo `src/server.py`.
- frontend Three.js, por ejemplo `web/index.html`, `web/app.js`, `web/styles.css`.
- datos derivados ligeros en una carpeta `output/`, si hace falta.

## Restricciones

- Todo debe ejecutarse en local.
- No subir datos a servicios externos.
- No prometer precision milimetrica absoluta.
- El objetivo es una demo creible de control de calidad, no un sistema ferroviario certificado.
- Mantener el codigo simple y facil de explicar en una presentacion de hackathon.

## Mensaje del producto

El producto no sustituye una auscultacion certificada. Su valor es automatizar una primera verificacion de calidad de trabajos LiDAR: cobertura, huecos, sombras, consistencia de pasadas y zonas que deben revisarse antes de aceptar la captura.
