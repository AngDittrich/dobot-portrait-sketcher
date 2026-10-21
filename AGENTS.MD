En el directorio windows/ está todo el proyecto funcionando en windows y en android es el código para el apk que funciona en dispositivos android.

Dentro de windows/ el código está dividido en dos partes: `windows/frontend/` es la app React (Vite + TypeScript) de la cabina de fotos y `windows/backend/` es el servidor Python (FastAPI + OpenCV/ONNX) que hace el boceto, la vectorización y el control del robot Dobot MG400.

El agente debe verificar en que rama está antes de subir cambios al repositorio de GitHub. Si eres Angel Ortega deberás trabajar sobre tu rama y si eres Angel Dittrich sobre tu rama. Luego de estar trabajando en el proyecto es FUNDAMENTAL que después de cada serie de cambios vayas haciendo commits constantemente para tener un buen control de versiones, evitar un commit de 30+ archivos cambiados, sino hacer commits por funcionalidades, implementaciones, integraciones, arreglo de bugs, etc. Luego de haber hecho las series de commits, pushear a dicha rama y decirle al usuario si quiere hacer la Pull request hacia main que es la rama principal de producción.

REGLA DE DISEÑO (prioridad alta, del dueño del producto): ODIO el círculo verde que dice (LIVE) y ese tipo de labels/badges genéricos ("EN VIVO", dots de estado, pills decorativas, pasos "1/4") — se ven super genéricos y hechos por IA. Están PROHIBIDOS en el sitio. El estado de la interfaz se comunica con la composición, la luz y el movimiento, nunca con etiquetas obvias.

WIZARD DE LA CABINA (windows/): la experiencia es un wizard de una sola pantalla, sin scroll.
1. attract — el robot saluda (`assets/robot/dobotsayinghello.webp`) y el botón COMENZAR.
2. camera → countdown → capture — visor y cuenta regresiva.
3. reveal — la foto entra en iris y se transforma a sketch.
4. confirm — "¿Listo para ser dibujado?" con TOMAR OTRA (vuelve a camera) a la izquierda y ¡SÍ! a la derecha.
5. drawing (3 s) — `assets/robot/dobotidlemarker.webp` y el texto de que el robot está dibujando. Luego thanks: "LISTO. TOMA TU DIBUJO." y "SYSCOM agradece tu visita." Vuelve solo a attract.
Si una sección que espera al usuario no cambia en 3 minutos, todo se reinicia a attract. Las fotos del robot no se invierten de color; el filtro blanco es solo para el logo SYSCOM.