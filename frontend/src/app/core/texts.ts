/** All user-facing strings live here so they can be translated later. */
export const TEXTS = {
  appTitle: 'YouTube Downloader',
  engine: {
    heading: 'Motor de descarga',
    loading: 'Comprobando…',
    status: {
      missing: 'No instalado',
      installing: 'Instalando…',
      ready: 'Listo',
      error: 'Error',
    } as Record<string, string>,
    unknownStatus: 'Desconocido',
    versions: { ytDlp: 'yt-dlp', ffmpeg: 'ffmpeg', ffprobe: 'ffprobe', deno: 'Deno' },
    retry: 'Reintentar',
    update: 'Actualizar yt-dlp',
    updating: 'Actualizando…',
    actionFailed: 'No se pudo enviar la orden al servidor local.',
    updateFailed: 'No se pudo actualizar yt-dlp:',
  },
  health: {
    unreachable: 'No se pudo contactar con el servidor local.',
    version: 'Versión',
    port: 'Puerto',
  },
  shutdown: {
    button: 'Cerrar aplicación',
    closing: 'Cerrando…',
    done: 'La aplicación se cerró',
    doneHint: 'Ya puedes cerrar esta pestaña. Para volver a usarla, abre de nuevo la aplicación.',
    failed: 'No se pudo cerrar la aplicación.',
  },
} as const;
