# Onda — Community App Store para Umbrel

Empaqueta el extractor de audio (YouTube y SoundCloud → MP3) como **app de
Umbrel**, instalable desde un Community App Store propio alojado en GitHub. Una
vez instalada, aparece en el escritorio de Umbrel con su icono, su login
(vía `app_proxy`) y actualizaciones gestionadas desde la UI.

## Estructura del repo

```
yt2mp3/
├── umbrel-app-store.yml          # id + nombre del store (prefijo de las apps)
├── .github/workflows/build.yml   # compila la imagen y la sube a GHCR
├── app-src/                       # contexto de build de la imagen
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── core.py                    # motor: yt-dlp + FFmpeg
│   └── app.py                     # servidor Flask (gunicorn)
└── borjarodmar-yt2mp3/            # la app (la carpeta DEBE llamarse como el id)
    ├── umbrel-app.yml             # manifiesto que ve la UI de Umbrel
    ├── docker-compose.yml         # app_proxy + servicio
    └── icon.svg                   # icono de la app
```

Clave de Umbrel: el `id` del store es prefijo obligatorio del `id` de la app, y
la **carpeta de la app debe llamarse exactamente igual** que ese id.

## Por qué hace falta publicar una imagen

Umbrel **no compila tu Dockerfile**: descarga una imagen ya publicada en un
registro. Por eso el `docker-compose.yml` de la app apunta a una imagen en GHCR,
y el GitHub Action se encarga de construirla multi-arch (ARM64 y amd64, para que
funcione tanto en una Raspberry Pi como en un mini PC) y subirla.

## Puesta en marcha (una sola vez)

1. **Sube este repo a tu GitHub** (p. ej. `yt2mp3`).

2. **Sustituye el usuario de GitHub** por el tuyo donde aparezca:
   - `docker-compose.yml` de la app (línea `image:`, en minúsculas)
   - `umbrel-app.yml` (urls e icono, opcional)

3. **Deja que el Action publique la imagen.** Se dispara solo al hacer push.
   También puedes lanzarlo a mano desde la pestaña *Actions* (Run workflow).

4. **Haz público el paquete GHCR.** En GitHub → tu perfil → *Packages* → el
   paquete → *Package settings* → *Change visibility* → **Public**. (Si no,
   Umbrel no podrá descargarlo sin credenciales.)

5. **Añade el store en Umbrel.** En la UI: App Store → menú (⋯) → *Community App
   Stores* → pega la URL de tu repo de GitHub.

6. **Instala la app** desde tu store. Listo.

## Uso

Abre la app desde el escritorio de Umbrel. Si accedes en remoto (por ejemplo con
una VPN o un túnel tipo Tailscale), entra al host de tu Umbrel y ábrela igual; el
`app_proxy` te pide el login de Umbrel. En el dispositivo desde el que la usas no
necesitas instalar nada: solo el navegador. Pega un enlace de YouTube o
SoundCloud, pulsa **Analizar**, elige la calidad y descarga el MP3.

## Actualizar yt-dlp (cuando una plataforma cambie sus firmas)

1. Sube el `version` en `umbrel-app.yml` (p. ej. `1.0.1`).
2. Haz push a `main` (o crea un tag `vX.Y.Z`).
3. El Action reconstruye y publica la imagen.
4. En Umbrel aparecerá la actualización.

(Como `requirements.txt` no fija la versión de yt-dlp, cada build trae la última.)

## Dónde quedan los MP3

El MP3 se genera en una carpeta temporal del contenedor, se envía al navegador
como descarga y se borra del servidor. Acaba en las descargas de tu dispositivo
y no se acumula nada en Umbrel. El volumen de datos de la app solo guarda la
caché de yt-dlp.

## Notas

- Conversión **síncrona** (gunicorn con `--timeout 600`): para audios largos el
  navegador espera. Suficiente para uso personal.
- Solo para uso legítimo (contenido propio o con licencia libre).
