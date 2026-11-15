import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  Observable,
  Subject,
  catchError,
  debounce,
  map,
  of,
  startWith,
  switchMap,
  timer,
} from 'rxjs';
import { EngineService } from '../core/engine.service';
import { MediaPreview, PreviewError, PreviewService, Quality } from '../core/preview.service';
import { TEXTS } from '../core/texts';

export const DEBOUNCE_MS = 500;
export const QUALITIES: readonly Quality[] = ['best', '2160p', '1080p', '720p', '480p'];

type Status = 'idle' | 'loading' | 'ready' | 'error';
type Outcome =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'error'; code: string }
  | { state: 'ready'; media: MediaPreview };
type Request = { url: string; immediate: boolean };

/** Cheap client-side filter: only input that could be a link triggers a request. */
export function looksLikeUrl(value: string): boolean {
  return /^(https?:\/\/)?[^\s/.]+(\.[^\s/.]+)+(\/\S*)?$/i.test(value.trim());
}

/** `75` -> `1:15`, `3725` -> `1:02:05`. */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}

/** URL field with automatic preview: debounced typing, immediate on paste, stale requests cancelled. */
@Component({
  selector: 'app-url-preview',
  templateUrl: './url-preview.html',
  styleUrl: './url-preview.css',
})
export class UrlPreview {
  private readonly previews = inject(PreviewService);
  protected readonly engineReady = inject(EngineService).engineReady;
  private readonly requests = new Subject<Request>();

  protected readonly texts = TEXTS;
  protected readonly qualities = QUALITIES;
  protected readonly url = signal('');
  protected readonly status = signal<Status>('idle');
  protected readonly preview = signal<MediaPreview | null>(null);
  protected readonly errorCode = signal<string | null>(null);
  protected readonly errorMessage = computed(() => {
    const code = this.errorCode();
    return code ? (TEXTS.preview.errors[code] ?? TEXTS.preview.errors['unknown']) : null;
  });
  /** The Quality picked in the selector; ticket 05 reads it to enqueue. */
  readonly quality = signal<Quality>('best');

  constructor() {
    this.requests
      .pipe(
        debounce((request) => (request.immediate ? of(0) : timer(DEBOUNCE_MS))),
        map((request) => request.url.trim()),
        // switchMap unsubscribes from the previous request, which aborts its HTTP call.
        switchMap((url): Observable<Outcome> => {
          if (!looksLikeUrl(url)) {
            return of({ state: 'idle' });
          }
          return this.previews.fetch(url).pipe(
            map((media): Outcome => ({ state: 'ready', media })),
            startWith<Outcome>({ state: 'loading' }),
            catchError((error: unknown) =>
              of<Outcome>({
                state: 'error',
                code: error instanceof PreviewError ? error.code : 'unknown',
              }),
            ),
          );
        }),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe((result) => this.apply(result));

    // Losing the Engine (e.g. while it updates) blocks the field; drop what is on screen.
    effect(() => {
      if (!this.engineReady()) {
        this.reset();
      }
    });
  }

  protected onInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.url.set(value);
    // A paste is a complete link: no need to wait for more keystrokes.
    const inputType = (event as InputEvent).inputType ?? '';
    this.schedule(value, inputType === 'insertFromPaste' || inputType === 'insertFromDrop');
  }

  protected showFullPlaylist(playlistUrl: string): void {
    this.url.set(playlistUrl);
    this.schedule(playlistUrl, true);
  }

  protected qualityLabel(quality: Quality): string {
    if (quality === 'best') {
      return TEXTS.preview.qualityBest;
    }
    return quality === '2160p' ? `${quality} (${TEXTS.preview.quality2160Hint})` : quality;
  }

  protected isAvailable(preview: MediaPreview, quality: Quality): boolean {
    return preview.availableQualities.includes(quality);
  }

  protected duration(seconds: number): string {
    return formatDuration(seconds);
  }

  protected selectQuality(value: string): void {
    this.quality.set(value as Quality);
  }

  private schedule(url: string, immediate: boolean): void {
    // Anything pending or in flight is stale from now on: clear the old result right away.
    if (!looksLikeUrl(url)) {
      this.reset();
    }
    this.requests.next({ url, immediate });
  }

  private apply(outcome: Outcome): void {
    switch (outcome.state) {
      case 'idle':
        this.reset();
        break;
      case 'loading':
        this.preview.set(null);
        this.errorCode.set(null);
        this.status.set('loading');
        break;
      case 'error':
        this.preview.set(null);
        this.errorCode.set(outcome.code);
        this.status.set('error');
        break;
      case 'ready':
        this.preview.set(outcome.media);
        this.errorCode.set(null);
        this.quality.set('best');
        this.status.set('ready');
        break;
    }
  }

  private reset(): void {
    this.status.set('idle');
    this.preview.set(null);
    this.errorCode.set(null);
  }
}
