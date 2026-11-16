import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { EngineService } from './engine.service';
import { ErrorLogEntry } from './error-log.service';
import { SystemService } from './system.service';

export const LOG_LINES = 500;

@Injectable({ providedIn: 'root' })
export class LogsService {
  private readonly http = inject(HttpClient);
  private readonly engine = inject(EngineService);
  private readonly system = inject(SystemService);

  /** The tail of the server log; requests (`uvicorn.access`) only on demand. */
  fetch(includeRequests: boolean): Observable<string[]> {
    return this.http
      .get<{ lines: string[] }>('/api/logs', {
        params: { lines: LOG_LINES, requests: includeRequests },
      })
      .pipe(map((body) => body.lines));
  }

  /** Header plus both sources, as plain text to copy or download. */
  report(
    serverLines: readonly string[],
    frontend: readonly ErrorLogEntry[],
    includesRequests: boolean,
    now: Date,
  ): string {
    const versions = this.engine.engine()?.versions;
    const engine = versions
      ? [
          ['yt-dlp', versions.ytDlp],
          ['ffmpeg', versions.ffmpeg],
          ['ffprobe', versions.ffprobe],
          ['Deno', versions.deno],
        ]
          .map(([name, value]) => `${name} ${value ?? 'desconocido'}`)
          .join(', ')
      : 'desconocido';
    const header = [
      'YouTube Downloader: registros',
      `Fecha: ${now.toISOString()}`,
      `Versión de la app: ${this.system.version() ?? 'desconocida'}`,
      `Plataforma: ${this.system.platform() ?? 'desconocida'}`,
      `Engine: ${engine}`,
    ];
    const server = [
      `== Registro del servidor (últimas ${serverLines.length} líneas${
        includesRequests ? ', con peticiones' : ', sin peticiones'
      }) ==`,
      ...(serverLines.length ? serverLines : ['(vacío)']),
    ];
    const tab = [
      `== Errores del frontend (${frontend.length}) ==`,
      ...(frontend.length
        ? frontend.map((e) => `${e.at} [${e.kind}] ${e.message}`)
        : ['(ninguno)']),
    ];
    return [...header, '', ...server, '', ...tab, ''].join('\n');
  }
}
