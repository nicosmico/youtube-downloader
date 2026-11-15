import { Injectable, InjectionToken, OnDestroy, inject } from '@angular/core';

/** Creates the EventSource of the server stream; replaced by a fake in tests. */
export const EVENT_SOURCE_FACTORY = new InjectionToken<(url: string) => EventSource>(
  'EVENT_SOURCE_FACTORY',
  { providedIn: 'root', factory: () => (url: string) => new EventSource(url) },
);

export type StreamListener = (event: Event) => void;

/** The one `GET /api/events` connection of the app, shared by every live service. */
@Injectable({ providedIn: 'root' })
export class EventStreamService implements OnDestroy {
  private readonly createSource = inject(EVENT_SOURCE_FACTORY);
  private source: EventSource | null = null;
  private readonly listeners: [string, StreamListener][] = [];

  /** Registers a listener; works before and after `connect()`. `open` fires on every reconnect. */
  on(name: string, listener: StreamListener): void {
    this.listeners.push([name, listener]);
    this.source?.addEventListener(name, listener);
  }

  /** Opens the stream (idempotent). */
  connect(): void {
    if (this.source) {
      return;
    }
    const source = this.createSource('/api/events');
    for (const [name, listener] of this.listeners) {
      source.addEventListener(name, listener);
    }
    this.source = source;
  }

  close(): void {
    this.source?.close();
    this.source = null;
  }

  ngOnDestroy(): void {
    this.close();
  }
}

/** The JSON payload of a server event. */
export function eventData<T>(event: Event): T {
  return JSON.parse((event as MessageEvent<string>).data) as T;
}
