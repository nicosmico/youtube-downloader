import { HttpClient } from '@angular/common/http';
import { Injectable, OnDestroy, computed, inject, signal } from '@angular/core';
import { EventStreamService, eventData } from './event-stream.service';

export { EVENT_SOURCE_FACTORY } from './event-stream.service';

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

/** Live Engine state: REST for commands and rehydration, SSE (`engine.updated`) for changes. */
@Injectable({ providedIn: 'root' })
export class EngineService implements OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly stream = inject(EventStreamService);
  private connected = false;

  readonly engine = signal<EngineInfo | null>(null);
  /** True once the Engine is `ready`: the enqueue and preview UI use this to block actions. */
  readonly engineReady = computed(() => this.engine()?.status === 'ready');
  readonly actionError = signal(false);

  /** Opens the event stream (idempotent). On every (re)connect the state is fetched again. */
  connect(): void {
    if (this.connected) {
      return;
    }
    this.connected = true;
    this.stream.on('open', () => this.refresh());
    this.stream.on('engine.updated', (event) => this.engine.set(eventData<EngineInfo>(event)));
    this.stream.connect();
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
    this.stream.close();
  }

  private command(url: string): void {
    this.actionError.set(false);
    this.http.post<EngineInfo>(url, null).subscribe({
      next: (info) => this.engine.set(info),
      error: () => this.actionError.set(true),
    });
  }
}
