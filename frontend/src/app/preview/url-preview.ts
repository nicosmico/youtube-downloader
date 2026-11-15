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
import { AudioFormat, DownloadOptions, EnqueueError, JobsService } from '../core/jobs.service';
import { MediaPreview, PreviewError, PreviewService, Quality } from '../core/preview.service';
import { Preset } from '../core/presets.service';
import { TEXTS } from '../core/texts';
import { Presets } from '../presets/presets';

export const DEBOUNCE_MS = 500;
export const QUALITIES: readonly Quality[] = ['best', '2160p', '1080p', '720p', '480p'];
export const AUDIO_FORMATS: readonly AudioFormat[] = ['m4a', 'mp3', 'opus'];
/** `m4a`: YouTube's own AAC stream is saved as is (no re-encoding, no loss) and plays everywhere. */
export const DEFAULT_AUDIO_FORMAT: AudioFormat = 'm4a';
export type Mode = 'video' | 'audio';

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

/** Spanish text for a rejected enqueue: a known code, else the server's own message. */
function enqueueMessage(error: unknown): string {
  const texts = TEXTS.preview;
  if (!(error instanceof EnqueueError)) {
    return texts.enqueueErrors['unknown'];
  }
  return (
    texts.enqueueErrors[error.code] ??
    texts.errors[error.code] ??
    (error.message || texts.enqueueErrors['unknown'])
  );
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
  imports: [Presets],
  templateUrl: './url-preview.html',
  styleUrl: './url-preview.css',
})
export class UrlPreview {
  private readonly previews = inject(PreviewService);
  private readonly jobs = inject(JobsService);
  protected readonly engineReady = inject(EngineService).engineReady;
  private readonly requests = new Subject<Request>();

  protected readonly texts = TEXTS;
  protected readonly qualities = QUALITIES;
  protected readonly audioFormats = AUDIO_FORMATS;
  protected readonly url = signal('');
  protected readonly status = signal<Status>('idle');
  protected readonly preview = signal<MediaPreview | null>(null);
  protected readonly errorCode = signal<string | null>(null);
  protected readonly errorMessage = computed(() => {
    const code = this.errorCode();
    return code ? (TEXTS.preview.errors[code] ?? TEXTS.preview.errors['unknown']) : null;
  });
  /** What the user picked; "Descargar" enqueues with it. It survives previewing the next URL. */
  readonly mode = signal<Mode>('video');
  readonly quality = signal<Quality>('best');
  readonly audioFormat = signal<AudioFormat>(DEFAULT_AUDIO_FORMAT);
  protected readonly enqueuing = signal(false);
  protected readonly enqueued = signal(false);
  protected readonly enqueueError = signal<string | null>(null);

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

  protected audioFormatLabel(format: AudioFormat): string {
    return TEXTS.preview.audioFormats[format];
  }

  protected selectMode(mode: Mode): void {
    this.mode.set(mode);
  }

  protected selectAudioFormat(value: string): void {
    this.audioFormat.set(value as AudioFormat);
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

  /** One click: mode plus its quality or format. A quality this video lacks falls back to best. */
  protected applyPreset(media: MediaPreview, preset: Preset): void {
    this.mode.set(preset.mode);
    if (preset.mode === 'audio') {
      this.audioFormat.set(preset.audioFormat ?? DEFAULT_AUDIO_FORMAT);
      return;
    }
    const quality = preset.quality ?? 'best';
    this.quality.set(media.availableQualities.includes(quality) ? quality : 'best');
  }

  protected selectQuality(value: string): void {
    this.quality.set(value as Quality);
  }

  protected download(media: MediaPreview): void {
    if (!this.engineReady() || this.enqueuing()) {
      return;
    }
    this.enqueuing.set(true);
    this.enqueued.set(false);
    this.enqueueError.set(null);
    const options: DownloadOptions =
      this.mode() === 'audio'
        ? { mode: 'audio', audioFormat: this.audioFormat() }
        : { mode: 'video', quality: this.quality() };
    this.jobs.enqueue(media.url, options, media.title).subscribe({
      next: () => {
        this.enqueuing.set(false);
        this.enqueued.set(true);
      },
      error: (error: unknown) => {
        this.enqueuing.set(false);
        this.enqueueError.set(enqueueMessage(error));
      },
    });
  }

  private schedule(url: string, immediate: boolean): void {
    // Anything pending or in flight is stale from now on: clear the old result right away.
    if (!looksLikeUrl(url)) {
      this.reset();
    }
    this.requests.next({ url, immediate });
  }

  private apply(outcome: Outcome): void {
    this.enqueued.set(false);
    this.enqueueError.set(null);
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
        // The pick is kept for the next video unless this one cannot offer that Quality.
        if (!outcome.media.availableQualities.includes(this.quality())) {
          this.quality.set('best');
        }
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
