# MVP de validacion LiDAR ferroviaria

## Descripcion

Este repositorio contiene la base documental para una primera version de una herramienta local de validacion de calidad LiDAR aplicada a infraestructura ferroviaria.

La idea del hackathon es simular un sistema de drones embarcados en una bateadora que revisan si una captura LiDAR se ha hecho correctamente. El sistema carga una nube de puntos `.laz`, construye una escena 3D sencilla y calcula metricas basicas de cobertura para decidir si el trabajo es aceptable o si hay zonas que deberian repetirse.

Archivo de prueba incluido en el workspace:

- `PNOA_2020_AND-C_364-4210_ORT-CLA-RGB.laz`

## Objetivo

El objetivo del MVP es demostrar, en pocas horas, que se puede crear una herramienta local capaz de:

- cargar una nube LiDAR en formato `.laz`,
- visualizar el terreno en 3D,
- analizar una zona corta de via y talud,
- calcular densidad y cobertura por rejilla,
- simular varias pasadas de drones,
- marcar zonas con buena cobertura, cobertura irregular o huecos,
- generar una explicacion visual de como se validaria un trabajo LiDAR real.

## Alcance de la demo

La demo no pretende certificar geometricamente una obra ferroviaria ni sustituir una revision topografica oficial. El objetivo es mostrar una capa de QA preliminar para detectar problemas evidentes antes de aceptar una captura LiDAR.

El mensaje tecnico correcto es:

- precision absoluta con GNSS europeo: escala decimetrica en condiciones nominales;
- repetibilidad local: puede mejorar con varias pasadas, buena calibracion y referencia rigida del tren;
- valor del sistema: detectar huecos, sombras, baja densidad, solapes insuficientes y zonas que hay que repetir.

## Flujo de trabajo propuesto

1. El usuario carga el archivo `.laz`.
2. El sistema lee la nube de puntos y calcula metricas generales.
3. Se selecciona una zona de analisis, por ejemplo 20 metros de via con un talud.
4. La herramienta divide la zona en una rejilla 2D.
5. Para cada celda calcula densidad, rango de cotas y cobertura.
6. Se simulan varias pasadas de dron desde diferentes posiciones.
7. El sistema genera un mapa QA con colores.
8. La demo muestra si la captura se acepta o si hay que repetir zonas concretas.

## Que harian los drones en cada pasada

### Pasada 1: reconocimiento general

El primer dron realiza una pasada principal siguiendo el eje del tramo ferroviario.

Su funcion es capturar una vista global de la plataforma, la via, el balasto, el entorno inmediato y el talud. Esta pasada sirve para crear una primera referencia visual y geometrica del corredor.

En el sistema QA, esta pasada permite detectar:

- extension general del tramo,
- zonas sin puntos,
- huecos grandes,
- problemas evidentes de cobertura,
- diferencias importantes entre la geometria esperada y la nube observada.

### Pasada 2: refuerzo lateral derecho

El segundo dron se desplaza hacia el lateral derecho del corredor o cambia el angulo de observacion.

Su funcion es reducir sombras y oclusiones que aparecen cuando el terreno, el talud o los elementos de via se observan desde un unico punto de vista.

Esta pasada es especialmente util para:

- caras laterales del talud,
- cunetas,
- pie del talud,
- bordes de plataforma,
- zonas donde la primera pasada tenia baja densidad.

### Pasada 3: refuerzo lateral izquierdo o zona de sombra

El tercer dron cubre el lado opuesto o se concentra en las areas que el sistema ha marcado como irregulares.

Su funcion es confirmar si las zonas dudosas son un fallo real de captura o simplemente una limitacion del primer angulo de observacion.

Esta pasada ayuda a mejorar:

- densidad local,
- continuidad de la nube,
- consistencia entre observaciones,
- visibilidad de zonas parcialmente ocultas.

### Pasada 4 opcional: pasada adaptativa de reparacion

Si despues de las tres primeras pasadas el mapa QA sigue mostrando celdas rojas, el sistema genera una pasada adaptativa.

Esta pasada no recorre todo el tramo. Solo se dirige a las zonas donde la cobertura es insuficiente.

Su objetivo es reducir coste operativo y evitar repetir una captura completa cuando solo fallan areas concretas.

## Resultado QA

El MVP puede usar un semaforo simple:

- Verde: densidad suficiente y cobertura continua.
- Amarillo: cobertura parcial, densidad irregular o zona que requiere revision.
- Rojo: hueco, sombra, baja densidad o captura insuficiente.

Metricas minimas recomendadas:

- numero total de puntos,
- bounding box X/Y/Z,
- rango altimetrico,
- densidad media de puntos por metro cuadrado,
- porcentaje de celdas verdes,
- porcentaje de celdas amarillas,
- porcentaje de celdas rojas,
- score QA de 0 a 100.

## Narrativa para el hackathon

La frase de producto puede ser:

> Capturar LiDAR no es lo mismo que verificar LiDAR. Nuestro sistema crea un gemelo digital local y usa drones embarcados para comprobar automaticamente si el trabajo tiene cobertura suficiente o si hay zonas que deben repetirse.

La tesis de la demo es simple:

- con una sola pasada pueden quedar sombras y huecos;
- con varias pasadas se mejora la cobertura;
- con una referencia embarcada y GNSS europeo se mantiene una trazabilidad soberana;
- con IA o reglas QA se automatiza la decision de aceptar, revisar o repetir.

## Datos y soberania tecnologica

Para una demo en Espana, la base gratuita mas adecuada es PNOA LiDAR, distribuida por CNIG. Sirve para construir un gemelo digital base de terreno, taludes y entorno.

Para el relato de posicionamiento soberano europeo:

- Galileo puede actuar como base GNSS europea.
- Galileo HAS permite hablar de posicionamiento de alta precision en escala decimetrica.
- EGNOS aporta mejora de prestaciones e integridad para operaciones relacionadas con drones y aviacion.

La demo debe ser honesta: no se debe prometer precision milimetrica absoluta con GNSS. La mejora fuerte se defiende como repetibilidad local y mejor cobertura al fusionar varias pasadas.

## Implementacion tecnica sugerida

Primera version implementada:

- Python para lectura y procesado `.laz`.
- `laspy` y `lazrs` para leer LAZ.
- `numpy` para calculo de rejillas y metricas.
- servidor local con la libreria estandar de Python.
- Three.js para visualizar nube, terreno, drones y mapa QA.

Estructura posible:

```text
.
|-- PNOA_2020_AND-C_364-4210_ORT-CLA-RGB.laz
|-- PROMPT_MVP.md
|-- README.md
|-- requirements.txt
|-- package.json
|-- run_mvp.bat
|-- src/
|   |-- process_laz.py
|   `-- server.py
|-- web/
|   |-- index.html
|   |-- app.js
|   `-- styles.css
`-- output/
    `-- sample_points.json
```

## Como arrancarlo en Windows

La forma rapida es ejecutar:

```bat
run_mvp.bat
```

El script hace lo siguiente:

1. Crea un entorno virtual `.venv` si no existe.
2. Instala las dependencias Python de `requirements.txt`.
3. Instala Three.js con `npm install` si falta `node_modules`.
4. Arranca el servidor local en `http://127.0.0.1:8000`.
5. Abre el navegador con la aplicacion.

Tambien se puede arrancar manualmente:

```bat
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
npm install
python src\server.py --host 127.0.0.1 --port 8000
```

Despues abre `http://127.0.0.1:8000` en el navegador.

## Que incluye el programa

- API `/api/files` para localizar archivos `.las` y `.laz` en la raiz del proyecto.
- API `/api/analyze` para procesar el archivo por chunks.
- Muestreo de puntos para que el navegador pueda representar la escena.
- Calculo de bounding box, densidad, rango Z y cobertura por rejilla.
- Generacion de `output/last_analysis.json` con el ultimo analisis.
- Visor Three.js con nube de puntos, via esquematica, corredor, mapa QA y drones animados.
- Botones para analizar el LAZ, mostrar/ocultar QA y animar las pasadas.
- Estimacion automatica del eje de via mediante PCA 2D sobre la nube de puntos del corredor.
- Simulacion de bateadora avanzando sobre el eje de via.
- Planificador matematico de pasadas de dron con reduccion de error residual.
- Informe automatico en `output/informe_qa.html` y `output/informe_qa.md`.
- Demo estatica en `docs/` para GitHub Pages y Vercel sin subir el archivo `.laz`.

## Enfoque matematico implementado

La herramienta no coloca la via a mano. Primero recorta el ROI del `.laz` y calcula el eje principal del corredor con PCA 2D sobre las coordenadas X/Y. Ese vector principal se usa como eje longitudinal de via, de forma que la via, la bateadora y las pasadas de dron se representan sobre la linea dominante de puntos.

Modelo simplificado:

```text
eje_via = autovector_principal(covarianza(X, Y))
s = proyeccion longitudinal sobre eje_via
d = proyeccion transversal sobre normal_via
```

Cada celda de la rejilla tiene un error antes y despues del paso de bateadora. Las pasadas de dron reducen la incertidumbre segun:

```text
e_i,k+1 = max(e_floor, e_i,k * (1 - g_k * visibilidad_i,k)) + anomalia_i
```

El planificador prioriza las celdas con mayor error residual y genera una cuarta pasada adaptativa hacia la zona critica.

## Simulacion antes/despues

El MVP simula un caso realista:

- Antes: via con irregularidad moderada y balasto heterogeneo junto al talud.
- Durante: la bateadora avanza por el eje de via y los drones cubren eje, laterales y zona critica.
- Despues: mejora general del tramo, pero queda una incidencia localizada de balasto/asiento residual.

Esa incidencia no perfecta se marca en rojo para que el sistema recomiende una repeticion localizada, no repetir toda la campana.

## GNSS y soberania

La narrativa tecnica usa una pila europea:

- Galileo Open Service como base GNSS.
- Galileo HAS para correcciones PPP de alta precision en escala decimetrica.
- EGNOS como capa de mejora e integridad operacional.
- IMU embarcada y referencia rigida de la bateadora para mejorar repetibilidad local.
- Procesado local, sin subir la nube de puntos a servicios externos.

La demo comunica la precision de forma honesta: decimetrica absoluta en GNSS/HAS nominal y mejor repetibilidad local al fusionar varias pasadas, sin prometer milimetria absoluta.

## Demo estatica para compartir

Despues de ejecutar un analisis local, se puede generar la version estatica:

```bat
python src\build_static.py
```

Esto crea `docs/` con:

- visor web,
- Three.js local,
- `sample_analysis.json` con una muestra preprocesada,
- informe HTML.

Esta carpeta es la que se publica en GitHub Pages o Vercel. Asi los companeros pueden ver la demo sin descargar el `.laz` completo ni ejecutar Python.

## Primeras tareas de desarrollo

1. Leer el archivo `.laz` y mostrar sus metadatos.
2. Muestrear una parte de la nube para que el navegador no se bloquee.
3. Calcular bounding box y densidad media.
4. Generar una rejilla QA.
5. Pintar puntos en Three.js.
6. Anadir trayectorias animadas de drones.
7. Mostrar panel con metricas y semaforo.

## Coste de la solucion

Para el MVP de hackathon, el coste de datos puede ser practicamente cero porque se usa PNOA LiDAR y software local open source.

En un piloto real, los costes principales estarian en:

- drones y sensores,
- receptor GNSS multibanda compatible con Galileo,
- integracion con la bateadora,
- calibracion y procedimientos de operacion,
- almacenamiento y procesado,
- validacion tecnica y normativa,
- mantenimiento de la plataforma.

El ahorro esperado no debe venderse como sustitucion total de topografia, sino como reduccion de retrabajos, deteccion temprana de fallos y decision rapida sobre que zonas repetir.

## Limitaciones

- El MVP puede usar reglas heuristicas en lugar de IA real.
- La deteccion automatica de via puede quedar fuera de la primera version.
- La seleccion de tramo puede ser manual o configurable.
- La precision del producto final depende de sensor, GNSS, IMU, calibracion, sincronizacion y geometria de pasadas.
- La herramienta no certifica seguridad ferroviaria.

## Evolucion futura

En siguientes versiones se podria incorporar:

- segmentacion automatica de via, plataforma, cuneta y talud,
- comparacion entre campanas LiDAR,
- alineamiento multi-pasada,
- deteccion de anomalias con modelos de IA,
- informes PDF automaticos,
- integracion GIS/BIM,
- simulacion de errores GNSS/IMU,
- gemelo digital historico del corredor.
