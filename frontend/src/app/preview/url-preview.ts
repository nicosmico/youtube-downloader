import {
  Component,
  DestroyRef,
  ElementRef,
  InjectionToken,
  computed,
  effect,
  inject,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import {
  Observable,
  Subject,
  catchError,
  debounce,
  defer,
  filter,
  map,
  of,
  startWith,
  switchMap,
  take,
  timer,
} from 'rxjs';
import { EngineService } from '../core/engine.service';
import { AudioFormat, DownloadOptions, EnqueueError, JobsService } from '../core/jobs.service';
import {
  MediaPreview,
  PlaylistEntry,
  PlaylistPreview,
  PreviewError,
  PreviewService,
  Quality,
} from '../core/preview.service';
import { TEXTS } from '../core/texts';
import { Dismissable } from '../ui/dismissable';
import { Icon } from '../ui/icon';
import { MenuKeys } from '../ui/menu-keys';
import { PRESETS, Preset } from './presets';

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
/** The playlist a video belongs to, loaded in the background to offer "Descargar N". */
type PlaylistLoad =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'failed' }
  | { state: 'ready'; playlist: PlaylistPreview };

/**
 * Whether "Pegar" is rendered: only where `readText` reads directly after the first permission
 * (Chromium). Detected by capability, not by user agent. Safari and Firefox paste with ⌘V/Ctrl+V.
 */
export function detectPasteSupport(): boolean {
  return 'userAgentData' in navigator && typeof navigator.clipboard?.readText === 'function';
}

/** Overridable in tests; the value is a function so it is evaluated per component. */
export const PASTE_SUPPORT = new InjectionToken<() => boolean>('PASTE_SUPPORT', {
  providedIn: 'root',
  factory: () => detectPasteSupport,
});

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
  imports: [Icon, Dismissable, MenuKeys],
  templateUrl: './url-preview.html',
})
export class UrlPreview {
  private readonly previews = inject(PreviewService);
  private readonly jobs = inject(JobsService);
  protected readonly engineService = inject(EngineService);
  protected readonly engineReady = this.engineService.engineReady;
  protected readonly engine = this.engineService.engine;
  private readonly field = viewChild<ElementRef<HTMLInputElement>>('field');
  private readonly requests = new Subject<Request>();
  /** A playlist URL to load in the background, or `null` to drop whatever is loading. */
  private readonly playlistRequests = new Subject<string | null>();
  private readonly readyChanges = toObservable(this.engineReady);
  protected readonly canPaste = inject(PASTE_SUPPORT)();

  protected readonly playlistLoad = signal<PlaylistLoad>({ state: 'idle' });
  /** The entries "Descargar N" would enqueue: the available ones of the loaded playlist. */
  private readonly playlistEntries = computed(() => {
    const load = this.playlistLoad();
    return load.state === 'ready' ? load.playlist.entries.filter((e) => e.available) : [];
  });
  /** "Descargar N" is offered while the playlist loads and once it has more than one video. */
  protected readonly playlistOffer = computed<'loading' | 'ready' | null>(() => {
    const load = this.playlistLoad();
    if (load.state === 'loading') {
      return 'loading';
    }
    return load.state === 'ready' && this.playlistEntries().length > 1 ? 'ready' : null;
  });

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
  /** Playlist: positions (`index`) of the entries that will be downloaded. */
  readonly selected = signal<ReadonlySet<number>>(new Set());
  protected readonly selectedCount = computed(() => this.selected().size);
  protected readonly enqueuing = signal(false);
  /** Which button was clicked, to say "Encolando…" on that one only. */
  private readonly enqueuingAll = signal(false);
  protected readonly enqueueError = signal<string | null>(null);
  protected readonly formatMenuOpen = signal(false);
  /** "Mejor video" and "MP3" are chips of their own; anything else lives under "Otro formato". */
  protected readonly bestActive = computed(
    () => this.mode() === 'video' && this.quality() === 'best',
  );
  protected readonly mp3Active = computed(
    () => this.mode() === 'audio' && this.audioFormat() === 'mp3',
  );
  protected readonly otherActive = computed(() => !this.bestActive() && !this.mp3Active());
  /** "Otro formato", or what was picked from it (`1080p`, `M4A`). */
  protected readonly otherLabel = computed(() => {
    if (!this.otherActive()) {
      return TEXTS.preview.format.other;
    }
    return this.mode() === 'audio'
      ? TEXTS.preview.format.audioFormats[this.audioFormat()]
      : this.quality();
  });

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
          return this.fetchWhenReady(url).pipe(startWith<Outcome>({ state: 'loading' }));
        }),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe((result) => this.apply(result));

    this.playlistRequests
      .pipe(
        switchMap((url): Observable<PlaylistLoad> => {
          if (url === null) {
            return of({ state: 'idle' });
          }
          return this.previews.fetch(url).pipe(
            map((media): PlaylistLoad =>
              media.kind === 'playlist' ? { state: 'ready', playlist: media } : { state: 'failed' },
            ),
            catchError(() => of<PlaylistLoad>({ state: 'failed' })),
            startWith<PlaylistLoad>({ state: 'loading' }),
          );
        }),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe((load) => this.playlistLoad.set(load));

    // Losing the Engine (e.g. while it updates) drops what is on screen. A request still waiting
    // for the Engine keeps its skeleton: it fires by itself once the Engine is ready.
    effect(() => {
      if (!this.engineReady() && untracked(this.status) !== 'loading') {
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
    this.setUrl(playlistUrl);
  }

  protected audioFormatLabel(format: AudioFormat): string {
    return TEXTS.preview.format.audioFormats[format];
  }

  protected qualityLabel(quality: Quality): string {
    if (quality === 'best') {
      return TEXTS.preview.format.best;
    }
    return quality === '2160p' ? `${quality} (${TEXTS.preview.format.vlcHint})` : quality;
  }

  /** A choice from the "Otro formato" menu. */
  protected pickVideo(quality: Quality, trigger: HTMLElement): void {
    this.mode.set('video');
    this.quality.set(quality);
    this.closeFormatMenu('pick', trigger);
  }

  protected pickAudio(format: AudioFormat, trigger: HTMLElement): void {
    this.mode.set('audio');
    this.audioFormat.set(format);
    this.closeFormatMenu('pick', trigger);
  }

  protected closeFormatMenu(reason: 'escape' | 'outside' | 'pick', trigger: HTMLElement): void {
    if (!this.formatMenuOpen()) {
      return;
    }
    this.formatMenuOpen.set(false);
    if (reason !== 'outside') {
      trigger.focus();
    }
  }

  /** Reads the clipboard; when the browser does not allow it, leaves the field focused to paste. */
  protected async paste(): Promise<void> {
    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (text) {
        this.setUrl(text);
        return;
      }
    } catch {
      // permission denied or no Clipboard API
    }
    this.field()?.nativeElement.focus();
  }

  protected clear(): void {
    this.setUrl('');
    this.field()?.nativeElement.focus();
  }

  private setUrl(value: string): void {
    this.url.set(value);
    this.schedule(value, true);
  }

  /** A playlist has no formats to look at (`--flat-playlist`): every quality is offered. */
  protected isAvailable(preview: MediaPreview, quality: Quality): boolean {
    return preview.kind === 'playlist' || preview.availableQualities.includes(quality);
  }

  protected toggleEntry(entry: PlaylistEntry): void {
    if (!entry.available) {
      return;
    }
    this.selected.update((current) => {
      const next = new Set(current);
      if (!next.delete(entry.index)) {
        next.add(entry.index);
      }
      return next;
    });
  }

  protected selectAllEntries(playlist: PlaylistPreview): void {
    this.selected.set(new Set(playlist.entries.filter((e) => e.available).map((e) => e.index)));
  }

  protected selectNoEntries(): void {
    this.selected.set(new Set());
  }

  protected downloadLabel(media: MediaPreview): string {
    const texts = TEXTS.preview;
    if (this.enqueuing() && !this.enqueuingAll()) {
      return texts.enqueuing;
    }
    if (media.kind === 'video') {
      return this.playlistOffer() ? texts.playlist.downloadOne : texts.download;
    }
    const n = this.selectedCount();
    return n === 1
      ? texts.playlist.downloadOne
      : texts.playlist.downloadMany.replace('{n}', String(n));
  }

  /** "Descargar N": the playlist a video came from, with every entry available. */
  protected downloadAllLabel(): string {
    const texts = TEXTS.preview;
    if (this.enqueuing() && this.enqueuingAll()) {
      return texts.enqueuing;
    }
    const load = this.playlistLoad();
    return load.state === 'ready'
      ? texts.playlist.downloadMany.replace('{n}', String(this.playlistEntries().length))
      : texts.playlist.downloadLoading;
  }

  protected canDownload(media: MediaPreview): boolean {
    return (
      this.engineReady() &&
      !this.enqueuing() &&
      (media.kind === 'video' || this.selectedCount() > 0)
    );
  }

  protected canDownloadAll(): boolean {
    return this.engineReady() && !this.enqueuing() && this.playlistOffer() === 'ready';
  }

  protected duration(seconds: number): string {
    return formatDuration(seconds);
  }

  /** One click: mode plus its quality or format. A quality this video lacks falls back to best. */
  protected readonly presets = PRESETS;

  protected applyPreset(media: MediaPreview, preset: Preset): void {
    this.formatMenuOpen.set(false);
    this.mode.set(preset.mode);
    if (preset.mode === 'audio') {
      this.audioFormat.set(preset.audioFormat ?? DEFAULT_AUDIO_FORMAT);
      return;
    }
    const quality = preset.quality ?? 'best';
    this.quality.set(this.isAvailable(media, quality) ? quality : 'best');
  }

  protected download(media: MediaPreview): void {
    if (!this.canDownload(media)) {
      return;
    }
    const entries =
      media.kind === 'playlist'
        ? media.entries.filter((e) => e.available && this.selected().has(e.index))
        : undefined;
    this.enqueue(media, entries, false);
  }

  /** "Descargar N" on a video that came from a playlist: the same as selecting all of it. */
  protected downloadAll(): void {
    const load = this.playlistLoad();
    if (!this.canDownloadAll() || load.state !== 'ready') {
      return;
    }
    this.enqueue(load.playlist, this.playlistEntries(), true);
  }

  private enqueue(media: MediaPreview, entries: PlaylistEntry[] | undefined, all: boolean): void {
    this.enqueuing.set(true);
    this.enqueuingAll.set(all);
    this.enqueueError.set(null);
    const options: DownloadOptions =
      this.mode() === 'audio'
        ? { mode: 'audio', audioFormat: this.audioFormat() }
        : { mode: 'video', quality: this.quality() };
    this.jobs
      .enqueue(
        media.url,
        options,
        media.title,
        entries?.map(({ id, url, index, title, thumbnail }) => ({
          id,
          url,
          index,
          title,
          thumbnail,
        })),
        media.kind === 'video' ? media.thumbnail : null,
      )
      .subscribe({
        next: () => {
          this.enqueuing.set(false);
          // The download shows up in the list: leave the field ready for the next link.
          this.clear();
        },
        error: (error: unknown) => {
          this.enqueuing.set(false);
          this.enqueueError.set(enqueueMessage(error));
        },
      });
  }

  /**
   * Waits for the Engine (a not-ready Engine is transient, never an error), then asks. A 409
   * `engine_not_ready` (race with the Engine state) waits for `ready` again and retries once.
   */
  private fetchWhenReady(url: string, retry = true): Observable<Outcome> {
    return this.whenEngineReady().pipe(
      switchMap(() => this.previews.fetch(url)),
      map((media): Outcome => ({ state: 'ready', media })),
      catchError((error: unknown) => {
        const code = error instanceof PreviewError ? error.code : 'unknown';
        if (code === 'engine_not_ready' && retry) {
          return this.fetchWhenReady(url, false);
        }
        return of<Outcome>({ state: 'error', code });
      }),
    );
  }

  private whenEngineReady(): Observable<boolean> {
    return defer(() =>
      this.engineReady() ? of(true) : this.readyChanges.pipe(filter(Boolean), take(1)),
    );
  }

  private schedule(url: string, immediate: boolean): void {
    // Anything pending or in flight is stale from now on: clear the old result right away.
    if (!looksLikeUrl(url)) {
      this.reset();
    }
    this.requests.next({ url, immediate });
  }

  private apply(outcome: Outcome): void {
    this.enqueueError.set(null);
    switch (outcome.state) {
      case 'idle':
        this.reset();
        break;
      case 'loading':
        this.playlistRequests.next(null);
        this.preview.set(null);
        this.errorCode.set(null);
        this.status.set('loading');
        break;
      case 'error':
        this.playlistRequests.next(null);
        this.preview.set(null);
        this.errorCode.set(outcome.code);
        this.status.set('error');
        break;
      case 'ready':
        this.preview.set(outcome.media);
        this.errorCode.set(null);
        // The pick is kept for the next video unless this one cannot offer that Quality.
        if (!this.isAvailable(outcome.media, this.quality())) {
          this.quality.set('best');
        }
        if (outcome.media.kind === 'playlist') {
          this.selectAllEntries(outcome.media);
        }
        this.status.set('ready');
        this.playlistRequests.next(
          outcome.media.kind === 'video' ? (outcome.media.playlistUrl ?? null) : null,
        );
        break;
    }
  }

  private reset(): void {
    this.playlistRequests.next(null);
    this.status.set('idle');
    this.preview.set(null);
    this.errorCode.set(null);
  }
}
