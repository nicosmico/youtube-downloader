import { HttpClient } from '@angular/common/http';
import { Injectable, InjectionToken, OnDestroy, computed, inject, signal } from '@angular/core';

export type EngineStatus = 'missing' | 'installing' | 'ready' | 'error';

export interface EngineInfo {
  status: EngineStatus;
  message: string | null;
  versions: {
    ytDlp: string | null;
    ffmpeg: string | null;
    ffprobe: string | null;
    deno: string | null;
  };
  updating: boolean;
  lastUpdateCheck: string | null;
  updateMessage: string | null;
}

/** Creates the EventSource of the server stream; replaced by a fake in tests. */
export const EVENT_SOURCE_FACTORY = new InjectionToken<(url: string) => EventSource>(
  'EVENT_SOURCE_FACTORY',
  { providedIn: 'root', factory: () => (url: string) => new EventSource(url) },
);

/** Live Engine state: REST for commands and rehydration, SSE (`engine.updated`) for changes. */
@Injectable({ providedIn: 'root' })
export class EngineService implements OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly createSource = inject(EVENT_SOURCE_FACTORY);
  private source: EventSource | null = null;

  readonly engine = signal<EngineInfo | null>(null);
  /** True once the Engine is `ready`: the enqueue and preview UI use this to block actions. */
  readonly engineReady = computed(() => this.engine()?.status === 'ready');
  readonly actionError = signal(false);

  /** Opens the event stream (idempotent). On every (re)connect the state is fetched again. */
  connect(): void {
    if (this.source) {
      return;
    }
    const source = this.createSource('/api/events');
    source.addEventListener('open', () => this.refresh());
    source.addEventListener('engine.updated', (event) => {
      this.engine.set(JSON.parse((event as MessageEvent<string>).data) as EngineInfo);
    });
    this.source = source;
  }

  refresh(): void {
    this.http.get<EngineInfo>('/api/system/engine').subscribe({
      next: (info) => this.engine.set(info),
      error: () => undefined,
    });
  }

  install(): void {
    this.command('/api/system/engine/install');
  }

  update(): void {
    this.command('/api/system/engine/update');
  }

  ngOnDestroy(): void {
    this.source?.close();
    this.source = null;
  }

  private command(url: string): void {
    this.actionError.set(false);
    this.http.post<EngineInfo>(url, null).subscribe({
      next: (info) => this.engine.set(info),
      error: () => this.actionError.set(true),
    });
  }
}
