import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { EngineInfo } from './engine.service';

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

@Injectable({ providedIn: 'root' })
export class SystemService {
  private readonly http = inject(HttpClient);

  /** Where the server runs (from `/api/health`); null until known. Labels host actions. */
  readonly platform = signal<string | null>(null);
  /** App version (from `/api/health`); null until known. */
  readonly version = signal<string | null>(null);
  /** Newer published version (from `/api/health` and the `app.update` event); null if none. */
  readonly update = signal<AppUpdate | null>(null);

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
