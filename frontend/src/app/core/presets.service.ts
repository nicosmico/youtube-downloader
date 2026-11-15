import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, tap, throwError } from 'rxjs';
import { AudioFormat, DownloadOptions } from './jobs.service';
import { Quality } from './preview.service';

/** A saved combination of DownloadMode with Quality or AudioFormat, as the API sends it. */
export interface Preset {
  id: string;
  name: string;
  mode: 'video' | 'audio';
  quality: Quality | null;
  audioFormat: AudioFormat | null;
  createdAt: string;
}

export const PRESET_NAME_MAX = 40;

/** A rejected request: the API `code` (or `network`/`unknown`) and the Spanish server message. */
export class PresetError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

const collator = new Intl.Collator('es', { sensitivity: 'base' });

function sortByName(presets: Preset[]): Preset[] {
  return [...presets].sort((a, b) => collator.compare(a.name, b.name));
}

/** The user's presets. The server is the source of truth; the list is loaded once at startup. */
@Injectable({ providedIn: 'root' })
export class PresetsService {
  private readonly http = inject(HttpClient);

  /** Sorted by name. */
  readonly presets = signal<Preset[]>([]);

  load(): void {
    this.http.get<Preset[]>('/api/presets').subscribe({
      next: (presets) => this.presets.set(sortByName(presets)),
      error: () => undefined,
    });
  }

  create(name: string, options: DownloadOptions): Observable<Preset> {
    return this.http.post<Preset>('/api/presets', { name, ...options }).pipe(
      tap((preset) => this.presets.update((list) => sortByName([...list, preset]))),
      catchError((error: unknown) => throwError(() => toPresetError(error))),
    );
  }

  rename(id: string, name: string): Observable<Preset> {
    return this.http.patch<Preset>(`/api/presets/${id}`, { name }).pipe(
      tap((preset) =>
        this.presets.update((list) => sortByName(list.map((p) => (p.id === id ? preset : p)))),
      ),
      catchError((error: unknown) => throwError(() => toPresetError(error))),
    );
  }

  remove(id: string): Observable<void> {
    return this.http.delete(`/api/presets/${id}`).pipe(
      tap(() => this.presets.update((list) => list.filter((p) => p.id !== id))),
      map(() => undefined),
      catchError((error: unknown) => throwError(() => toPresetError(error))),
    );
  }
}

function toPresetError(error: unknown): PresetError {
  if (!(error instanceof HttpErrorResponse)) {
    return new PresetError('unknown', '');
  }
  if (error.status === 0) {
    return new PresetError('network', '');
  }
  const body = error.error as { code?: string; message?: string } | null;
  return new PresetError(body?.code ?? 'unknown', body?.message ?? '');
}
