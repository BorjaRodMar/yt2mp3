"""
core.py — El "motor" del prototipo.

Aquí vive toda la lógica real, exactamente la misma cadena que usan las webs:
  1) Extraer metadatos del vídeo (sin descargar nada todavía).
  2) Descargar SOLO el stream de audio (formato nativo: Opus/AAC).
  3) Transcodificar a MP3 con FFmpeg (postprocesador de yt-dlp).
  4) Devolver la ruta del fichero final ya guardado en disco.

No sabe nada de interfaces (ni CLI ni web). Eso lo deciden las capas de encima.
"""

from pathlib import Path
import yt_dlp


# Carpeta donde se guardan los MP3 finales. La creamos si no existe.
CARPETA_SALIDA = Path(__file__).parent / "descargas"
CARPETA_SALIDA.mkdir(exist_ok=True)


def _hook_progreso(d: dict) -> None:
    """
    yt-dlp llama a esta función durante la descarga.
    Sirve para "ver" cómo ejecuta: estados típicos son
    'downloading' (bajando el stream) y 'finished' (stream completo,
    justo antes de que entre FFmpeg a transcodificar).
    """
    if d["status"] == "downloading":
        pct = d.get("_percent_str", "?").strip()
        velocidad = d.get("_speed_str", "?").strip()
        print(f"  [descargando audio] {pct}  a {velocidad}", end="\r")
    elif d["status"] == "finished":
        print("\n  [stream completo] -> pasando a FFmpeg para convertir a MP3...")


# Nombres bonitos para las plataformas que soportamos de forma explícita.
# yt-dlp soporta SoundCloud de forma nativa, así que el motor no cambia.
_PLATAFORMAS = {"youtube": "YouTube", "soundcloud": "SoundCloud"}


def _formato_duracion(segundos) -> str:
    """Convierte segundos en M:SS o H:MM:SS. Devuelve '—' si no hay dato."""
    if not segundos:
        return "—"
    segundos = int(segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    if horas:
        return f"{horas}:{minutos:02d}:{seg:02d}"
    return f"{minutos}:{seg:02d}"


def inspeccionar(url: str) -> dict:
    """
    FASE 1 — Solo metadatos. No descarga el medio.

    Es lo que hace la web nada más pegar el enlace: resuelve el ID,
    consulta la info y te enseña título, autor, duración y miniatura.
    El truco está en 'download': False. 'noplaylist' fuerza a tratar un
    enlace con contexto de lista como un único track.
    """
    opciones = {"quiet": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(url, download=False)

    clave = (info.get("extractor_key") or info.get("extractor") or "").lower()
    plataforma = _PLATAFORMAS.get(clave, info.get("extractor_key") or "Otra")

    return {
        "id": info.get("id"),
        "titulo": info.get("title"),
        "autor": info.get("uploader") or info.get("channel") or info.get("artist"),
        "duracion_seg": info.get("duration"),
        "duracion_txt": _formato_duracion(info.get("duration")),
        "miniatura": info.get("thumbnail"),
        "plataforma": plataforma,
    }



def descargar_mp3(url: str, bitrate: str = "192", carpeta: Path | None = None) -> Path:
    """
    FASES 2, 3 y 4 — Descarga el audio, lo convierte a MP3 y lo guarda.

    Parámetros:
      url     : enlace del vídeo de YouTube.
      bitrate : calidad del MP3 en kbps ('128', '192', '320'...).
      carpeta : carpeta de salida. Si es None, usa CARPETA_SALIDA (la CLI
                guarda ahí de forma persistente). La web le pasa una carpeta
                temporal para no dejar nada en disco.

    Devuelve la ruta (Path) del .mp3 final.

    Claves de la configuración de yt-dlp:
      - format 'bestaudio/best' : pide a YouTube el MEJOR stream de SOLO audio
                                  disponible (no descarga el vídeo, ahorra ancho
                                  de banda). yt-dlp resuelve por dentro el
                                  'signature cipher' que firma esas URLs.
      - outtmpl                 : plantilla del nombre de archivo. %(title)s y
                                  %(id)s se sustituyen por los datos reales.
      - postprocessors          : aquí entra FFmpeg. FFmpegExtractAudio coge el
                                  audio nativo (Opus/AAC) y lo recodifica a MP3
                                  con el bitrate pedido.
    """
    destino = carpeta if carpeta is not None else CARPETA_SALIDA
    plantilla_nombre = str(Path(destino) / "%(title)s [%(id)s].%(ext)s")

    opciones = {
        "format": "bestaudio/best",
        "outtmpl": plantilla_nombre,
        "noplaylist": True,
        "progress_hooks": [_hook_progreso],
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": bitrate,
            }
        ],
    }

    with yt_dlp.YoutubeDL(opciones) as ydl:
        # extract_info con download=True ejecuta TODA la cadena de una vez.
        info = ydl.extract_info(url, download=True)

        # prepare_filename nos da el nombre ANTES del postprocesado (.webm/.m4a).
        # Como FFmpeg lo convierte a mp3, forzamos la extensión final a .mp3.
        ruta_origen = Path(ydl.prepare_filename(info))
        ruta_final = ruta_origen.with_suffix(".mp3")

    return ruta_final
