# Cabina SYSCOM en Android

Envoltura de Capacitor sobre la app React de `windows/frontend`. La UI **no**
vive aquí: `webDir` apunta a `windows/frontend/dist`, así que se sigue editando
en un solo sitio y este proyecto sólo la empaqueta en un APK.

```
android/
  capacitor/        proyecto de Capacitor (config + gradle)
    android/        lo que abre Android Studio
  kotlin/           reservado, si algún día hace falta reescribir en nativo
```

## Requisitos

- Android Studio (trae el JDK y el SDK). Al abrirlo por primera vez acepta la
  instalación de **SDK Platform 36** y **Android SDK Platform-Tools**.
- Un teléfono o tablet con depuración USB activada.

## Flujo de trabajo

1. Compilar la UI apuntando al PC que tiene el robot:

   ```powershell
   $env:VITE_API_BASE = "http://192.168.10.3:8000"   # IP del PC, no del teléfono
   pnpm --dir windows/frontend build
   ```

   Si `VITE_API_BASE` se queda vacío, el APK busca la API en `https://localhost`
   y todo se queda en «convirtiendo»: es el error más común.

2. Copiar los assets al proyecto Android:

   ```powershell
   cd android/capacitor
   npx cap sync android
   ```

3. Compilar e instalar:

   ```powershell
   npx cap open android      # abre Android Studio y le das Run
   ```

   o por consola, con el teléfono conectado:

   ```powershell
   cd android
   .\gradlew.bat assembleDebug
   adb install -r app\build\outputs\apk\debug\app-debug.apk
   ```

## El backend tiene que escuchar en la red

Por defecto el backend se ata a `127.0.0.1`, que desde el teléfono no existe.
Para probar desde el dispositivo:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app
```

Y el teléfono tiene que estar en la **misma red** que el PC (el A55 en el Wi-Fi
de 192.168.10.0/24). Si Windows pregunta por el firewall, hay que permitir el
puerto 8000 en redes privadas.

## Ajustes que no son opcionales

| ajuste | dónde | por qué |
|---|---|---|
| `allowMixedContent` | `capacitor.config.ts` | La app se sirve desde `https://localhost` (eso es lo que hace funcionar la cámara, porque `getUserMedia` exige contexto seguro) y la API es `http://`. Sin esto el WebView bloquea la llamada. |
| `server.cleartext` + `usesCleartextTraffic` | config + `AndroidManifest.xml` | Android 9+ bloquea tráfico sin cifrar. |
| `<uses-permission CAMERA>` | `AndroidManifest.xml` | Sin declararlo no aparece ni el diálogo de permiso. |
| `screenOrientation="sensorLandscape"` | `AndroidManifest.xml` | El wizard es de una sola pantalla ancha. |
| CORS `https://localhost` | `windows/backend/app/main.py` | El origen del APK no es un puerto de Vite. |

## Si algo no prende

- **Pantalla en blanco**: falta correr `pnpm build` antes de `cap sync`, o
  `webDir` no resolvió. Revisa que `android/app/src/main/assets/public` tenga
  `index.html`.
- **La cámara no arranca**: niega el permiso una vez y Android no vuelve a
  preguntar. Se arregla en Ajustes → Apps → Cabina SYSCOM → Permisos → Cámara.
- **Se queda en «convirtiendo tu foto»**: la API no respondió. Comprueba
  `VITE_API_BASE`, que el backend esté en `--host 0.0.0.0` y que el teléfono
  abra `http://192.168.10.3:8000/api/health` en el navegador.
