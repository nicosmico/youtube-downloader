import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { EngineInfo } from './engine.service';
import { EventStreamService, eventData } from './event-stream.service';

export interface Health {
  app: string;
  version: string;
  engine: EngineInfo;
  port: number;
  /** `process.platform`-like: `darwin`, `win32` or `linux`. */
  platform?: string;
  /** A newer published version, if the startup check found one. */
  update?: AppUpdate | null;
}

export interface AppUpdate {
  version: string;
  url: string;
}

/** The folder where downloads are saved (`GET /api/settings/download-dir`). */
export interface DownloadDir {
  path: string;
  /** The path with the home folder shortened to `~`. */
  display: string;
  isDefault: boolean;
  /** The folder exists; false for a disconnected external drive. */
  available: boolean;
}

/** `choose` answer when the user closes the native dialog without picking a folder. */
export interface DownloadDirCanceled {
  canceled: true;
}

const DOWNLOAD_DIR_URL = '/api/settings/download-dir';

@Injectable({ providedIn: 'root' })
export class SystemService {
  private readonly http = inject(HttpClient);
  private readonly stream = inject(EventStreamService);
  private settingsConnected = false;

  /** Where the server runs (from `/api/health`); null until known. Labels host actions. */
  readonly platform = signal<string | null>(null);
  /** App version (from `/api/health`); null until known. */
  readonly version = signal<string | null>(null);
  /** Newer published version (from `/api/health` and the `app.update` event); null if none. */
  readonly update = signal<AppUpdate | null>(null);

  /** Download folder (from `GET /api/settings/download-dir` and `settings.updated`); null until known. */
  readonly downloadDir = signal<DownloadDir | null>(null);

  /** Keeps `downloadDir` live: fetched on every (re)connect of the event stream, then pushed. */
  connectSettings(): void {
    if (this.settingsConnected) {
      return;
    }
    this.settingsConnected = true;
    this.stream.on('open', () => this.refreshDownloadDir());
    this.stream.on('settings.updated', (event) =>
      this.downloadDir.set(eventData<DownloadDir>(event)),
    );
  }

  refreshDownloadDir(): void {
    this.http.get<DownloadDir>(DOWNLOAD_DIR_URL).subscribe({
      next: (dir) => this.downloadDir.set(dir),
      error: () => undefined,
    });
  }

  /** Opens the native folder dialog on the server; resolves when the user picks or cancels. */
  chooseDownloadDir(): Observable<DownloadDir | DownloadDirCanceled> {
    return this.http
      .post<DownloadDir | DownloadDirCanceled>(`${DOWNLOAD_DIR_URL}/choose`, null)
      .pipe(
        tap((result) => {
          if (!('canceled' in result)) {
            this.downloadDir.set(result);
          }
        }),
      );
  }

  /** Back to the default folder (Downloads). */
  resetDownloadDir(): Observable<DownloadDir> {
    return this.http
      .delete<DownloadDir>(DOWNLOAD_DIR_URL)
      .pipe(tap((dir) => this.downloadDir.set(dir)));
  }

  health(): Observable<Health> {
    return this.http.get<Health>('/api/health').pipe(
      tap((health) => {
        this.platform.set(health.platform ?? null);
        this.version.set(health.version);
        this.update.set(health.update ?? null);
      }),
    );
  }

  /** Host action: the server opens the Downloads folder in Finder/Explorer. */
  openDownloads(): Observable<{ status: string }> {
    return this.http.post<{ status: string }>('/api/system/open-downloads', null);
  }

  shutdown(): Observable<unknown> {
    return this.http.post('/api/system/shutdown', null);
  }
}
