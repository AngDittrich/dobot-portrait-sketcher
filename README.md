# 🤖🎨 Dobot Portrait Sketcher

[![Robot](https://img.shields.io/badge/Robot-Dobot%20MG400-blue)](https://www.dobot-scara.com/products/mg400.html)
[![Python](https://img.shields.io/badge/Python-3.8%2B-green)](https://www.python.org/)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-blue)](https://react.dev/)
[![Protocol](https://img.shields.io/badge/Protocol-TCP%2FIP-orange)](https://github.com/Dobot-Arm/TCP-IP-4Axis-Python)

**Dobot Portrait Sketcher** es una aplicación interactiva que combina **visión por computadora, interfaces web y robótica industrial**. Captura el retrato del usuario desde la interfaz web, procesa la imagen para convertirla en un dibujo en estilo sketch (líneas vectoriales) y controla un brazo robótico **Dobot MG400** para dibujar el retrato en papel en tiempo real.

---

## 🌟 Flujo de Experiencia del Usuario

1. **📸 Captura:** El usuario interactúa con la interfaz web, inicia una cuenta regresiva de 3 segundos y la cámara web toma la foto.
2. **🎨 Conversión a Sketch:** La imagen capturada es procesada en tiempo real mediante algoritmos de procesamiento de imagen (OpenCV) para extraer los bordes y trazos del rostro.
3. **👁️ Vista Previa:** El usuario revisa el boceto digital generado en la pantalla.
4. **🦾 Trazo Robótico:** Al confirmar, la secuencia de coordenadas $(X, Y, Z)$ es transmitida vía **TCP/IP** al controlador del Dobot MG400 para realizar el dibujo físicamente con un lápiz o plumón.

---

## 🏗️ Arquitectura del Sistema

El sistema se compone de tres módulos principales: