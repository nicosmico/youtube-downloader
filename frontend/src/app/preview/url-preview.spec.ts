import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FakeEventSource } from '../../testing/fake-event-source';
import { appHeaderInterceptor } from '../core/api.interceptor';
import { ENGINE_READY, MEDIA, PLAYLIST } from '../../testing/fixtures';
import { EVENT_SOURCE_FACTORY, EngineInfo, EngineService } from '../core/engine.service';
import { JobsService } from '../core/jobs.service';
import { DEBOUNCE_MS, UrlPreview, formatDuration, looksLikeUrl } from './url-preview';

const URL_A = 'https://www.youtube.com/watch?v=Jt5fgKBqZSY';
const URL_B = 'https://www.youtube.com/watch?v=jNQXAC9IVRw';

describe('UrlPreview', () => {
  let fixture: ComponentFixture<UrlPreview>;
  let http: HttpTestingController;
  let engine: EngineService;

  const root = () => fixture.nativeElement as HTMLElement;
  const el = <T extends HTMLElement>(testId: string) =>
    root().querySelector(`[data-testid=${testId}]`) as T | null;
  const input = () => el<HTMLInputElement>('url-input')!;
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const type = async (value: string, inputType = 'insertText') => {
    input().value = value;
    input().dispatchEvent(new InputEvent('input', { inputType, bubbles: true }));
    await settle();
  };
  const elapse = async (ms: number) => {
    vi.advanceTimersByTime(ms);
    await settle();
  };
  const previews = () => http.match('/api/preview');
  const openOther = async () => {
    el('format-other')!.click();
    await settle();
  };
  const pickFormat = async (testId: string) => {
    await openOther();
    el(testId)!.click();
    await settle();
  };
  const menuItems = () =>
    Array.from(
      root().querySelectorAll<HTMLButtonElement>('[data-testid=format-menu] [role=menuitemradio]'),
    );
  const pressKey = async (key: string) => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key }));
    await settle();
  };
  const answer = async (req: TestRequest, body: object | string, status = 200) => {
    req.flush(body, { status, statusText: 'x' });
    await settle();
  };

  beforeEach(async () => {
    // RxJS timers use setInterval; setTimeout and rAF stay real so Angular can stabilize.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    FakeEventSource.reset();
    await TestBed.configureTestingModule({
      imports: [UrlPreview],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    engine = TestBed.inject(EngineService);
    engine.engine.set(ENGINE_READY);
    fixture = TestBed.createComponent(UrlPreview);
    await settle();
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  describe('Engine not ready', () => {
    it('disables the field and the paste button, with a prominent notice', async () => {
      engine.engine.set({ ...ENGINE_READY, status: 'installing' } as EngineInfo);
      await settle();

      expect(input().disabled).toBe(true);
      expect(el<HTMLButtonElement>('paste-button')!.disabled).toBe(true);
      expect(el('engine-notice')?.getAttribute('role')).toBe('alert');
      expect(el('engine-notice')?.textContent).toContain('motor de descarga');
      expect(el('engine-notice-retry')).toBeNull();
      expect(el('empty-state')).toBeNull();
    });

    it('offers "Reintentar" with the message when the Engine failed', async () => {
      engine.engine.set({
        ...ENGINE_READY,
        status: 'error',
        message: 'sin conexión',
      } as EngineInfo);
      await settle();

      expect(el('engine-notice-message')?.textContent).toContain('sin conexión');
      el('engine-notice-retry')!.click();
      http.expectOne('/api/system/engine/install').flush({ ...ENGINE_READY, status: 'installing' });
    });

    it('enables it once the Engine is ready', async () => {
      expect(input().disabled).toBe(false);
      expect(el('engine-notice')).toBeNull();
    });

    it('clears what is on screen if the Engine stops being ready', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);
      expect(el('preview-card')).not.toBeNull();

      engine.engine.set({ ...ENGINE_READY, status: 'installing' } as EngineInfo);
      await settle();

      expect(el('preview-card')).toBeNull();
    });
  });

  describe('empty field', () => {
    it('shows a one-line empty state naming what is accepted, and no help text', () => {
      expect(el('empty-state')?.textContent).toContain('Videos, Shorts, playlists y canales');
      expect(input().placeholder).toBe('Pega un enlace de YouTube');
      expect(input().getAttribute('aria-label')).toBe('Enlace de YouTube');
      expect(root().textContent).not.toMatch(/Paso|\b1\.|Nota/);
    });

    it('hides the empty state while there is a preview', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      expect(el('empty-state')).toBeNull();
    });

    it('"Pegar" reads the clipboard and previews at once', async () => {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { readText: async () => `  ${URL_A}\n` },
      });

      el('paste-button')!.click();
      await settle();

      expect(input().value).toBe(URL_A);
      const req = http.expectOne('/api/preview');
      expect(req.request.body).toEqual({ url: URL_A });
      await answer(req, MEDIA);
    });

    it.each([
      ['is denied', () => Promise.reject(new Error('denied'))],
      ['is empty', () => Promise.resolve('   ')],
    ])('"Pegar" focuses the field when the clipboard %s', async (_, readText) => {
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { readText } });
      document.body.appendChild(root());

      el('paste-button')!.click();
      await settle();

      expect(document.activeElement).toBe(input());
      http.expectNone('/api/preview');
      root().remove();
    });

    it('"Pegar" focuses the field when there is no Clipboard API', async () => {
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
      document.body.appendChild(root());

      el('paste-button')!.click();
      await settle();

      expect(document.activeElement).toBe(input());
      root().remove();
    });

    it('clears the field with the X button', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      el('url-clear')!.click();
      await settle();

      expect(input().value).toBe('');
      expect(el('preview-card')).toBeNull();
      expect(el('empty-state')).not.toBeNull();
    });
  });

  describe('when to ask', () => {
    it('previews immediately on paste', async () => {
      await type(URL_A, 'insertFromPaste');

      const req = http.expectOne('/api/preview');
      expect(req.request.body).toEqual({ url: URL_A });
      await answer(req, MEDIA);
    });

    it('waits for the typing to pause (debounce)', async () => {
      await type(URL_A.slice(0, 30));
      await elapse(DEBOUNCE_MS - 100);
      await type(URL_A);
      await elapse(DEBOUNCE_MS - 1);
      expect(previews()).toHaveLength(0);

      await elapse(1);

      const req = http.expectOne('/api/preview');
      expect(req.request.body).toEqual({ url: URL_A });
      await answer(req, MEDIA);
    });

    it('does not ask for text that cannot be a link', async () => {
      await type('hola mundo', 'insertFromPaste');
      await type('hola');
      await elapse(DEBOUNCE_MS * 2);

      expect(previews()).toHaveLength(0);
      expect(el('preview-loading')).toBeNull();
      expect(el('preview-error')).toBeNull();
    });

    it('trims the pasted text', async () => {
      await type(`  ${URL_A}\n`, 'insertFromPaste');

      const req = http.expectOne('/api/preview');
      expect(req.request.body).toEqual({ url: URL_A });
      await answer(req, MEDIA);
    });

    it('lets the server judge links to other sites', async () => {
      await type('https://vimeo.com/123', 'insertFromPaste');

      await answer(http.expectOne('/api/preview'), { code: 'unsupported_site', message: 'x' }, 422);

      expect(el('preview-error')?.textContent).toContain('Solo se admiten enlaces de YouTube');
    });
  });

  describe('states', () => {
    it('shows the loading state until the answer arrives', async () => {
      await type(URL_A, 'insertFromPaste');

      expect(el('preview-loading')?.textContent).toContain('Obteniendo información');
      expect(el('preview-card')).toBeNull();

      await answer(http.expectOne('/api/preview'), MEDIA);

      expect(el('preview-loading')).toBeNull();
      expect(el('preview-card')).not.toBeNull();
    });

    it('shows a compact card: thumbnail with duration, title, author and maximum resolution', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), { ...MEDIA, duration: 3725 });

      expect(el('preview-title')?.textContent).toContain('Un Short vertical');
      expect(el('preview-author')?.textContent).toContain('YouTube');
      expect(el('preview-duration')?.textContent).toContain('1:02:05');
      expect(el('preview-max')?.textContent).toContain('Hasta 1080p');
      expect(el<HTMLImageElement>('preview-thumbnail')?.src).toBe(MEDIA.thumbnail);
    });

    it('groups every format under "Otro formato" and disables the video qualities above the maximum', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);
      expect(el('format-menu')).toBeNull();

      await openOther();

      expect(el('format-menu')?.getAttribute('role')).toBe('menu');
      expect(menuItems().map((o) => [o.dataset['testid'], o.disabled])).toEqual([
        ['format-video-best', false],
        ['format-video-2160p', true],
        ['format-video-1080p', false],
        ['format-video-720p', false],
        ['format-video-480p', false],
        ['format-audio-m4a', false],
        ['format-audio-mp3', false],
        ['format-audio-opus', false],
      ]);
      expect(menuItems()[0].textContent).toContain('Mejor disponible');
      expect(menuItems()[1].textContent).toContain('VLC');
      expect(el('format-menu')?.textContent).toContain('Video');
      expect(el('format-menu')?.textContent).toContain('Audio');
    });

    it('offers only "best" for a low resolution video', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), {
        ...MEDIA,
        availableQualities: ['best'],
        maxQuality: 'best',
        maxResolution: 240,
      });

      await openOther();
      const enabled = menuItems().filter(
        (o) => !o.disabled && o.dataset['testid']!.includes('video'),
      );
      expect(enabled.map((o) => o.dataset['testid'])).toEqual(['format-video-best']);
      expect(el('preview-max')?.textContent).toContain('240p');
    });

    it('hides the fields the video does not have', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), {
        ...MEDIA,
        thumbnail: null,
        author: null,
        duration: null,
        maxResolution: null,
      });

      for (const id of ['preview-thumbnail', 'preview-author', 'preview-duration', 'preview-max']) {
        expect(el(id)).toBeNull();
      }
      expect(el('preview-title')).not.toBeNull();
    });

    it('keeps the Quality the user picks and shows it on the third chip', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      await pickFormat('format-video-720p');

      expect(fixture.componentInstance.quality()).toBe('720p');
      expect(el('format-other')?.textContent).toContain('720p');
      expect(el('format-menu')).toBeNull();
    });

    it('shows the VLC hint on the 2160p option only', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), {
        ...MEDIA,
        availableQualities: ['best', '2160p', '1080p'],
        maxQuality: '2160p',
      });

      await openOther();
      expect(el('format-video-2160p')?.textContent).toContain('puede requerir VLC');
      expect(el<HTMLButtonElement>('format-video-2160p')!.disabled).toBe(false);
      expect(el('format-video-1080p')?.textContent).not.toContain('VLC');
    });

    it('clears the card when the field is emptied', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      await type('');
      await elapse(DEBOUNCE_MS);

      expect(el('preview-card')).toBeNull();
      expect(previews()).toHaveLength(0);
    });
  });

  describe('errors', () => {
    const cases: [string, number, string][] = [
      ['invalid_url', 422, 'no parece válido'],
      ['unsupported_site', 422, 'Solo se admiten enlaces de YouTube'],
      ['mix_playlist', 422, 'mixes automáticos'],
      ['live_content', 422, 'directos y estrenos'],
      ['not_public', 422, 'no es público'],
      ['unavailable', 422, 'no está disponible'],
      ['timeout', 504, 'tardó demasiado'],
      ['preview_failed', 502, 'No se pudo obtener la información'],
      ['engine_not_ready', 409, 'todavía no está listo'],
    ];

    for (const [code, status, text] of cases) {
      it(`shows a clear message for ${code}`, async () => {
        await type(URL_A, 'insertFromPaste');

        await answer(http.expectOne('/api/preview'), { code, message: 'ignored' }, status);

        const error = el('preview-error');
        expect(error?.textContent).toContain(text);
        expect(error?.getAttribute('data-code')).toBe(code);
        expect(el('preview-card')).toBeNull();
        expect(el('preview-loading')).toBeNull();
      });
    }

    it('says so when the local server cannot be reached', async () => {
      await type(URL_A, 'insertFromPaste');

      http.expectOne('/api/preview').error(new ProgressEvent('error'));
      await settle();

      expect(el('preview-error')?.textContent).toContain(
        'No se pudo contactar con el servidor local',
      );
    });

    it('falls back to a generic message for anything unexpected', async () => {
      await type(URL_A, 'insertFromPaste');

      await answer(http.expectOne('/api/preview'), 'oops', 500);

      expect(el('preview-error')?.textContent).toContain('error inesperado');
    });

    it('recovers: a new URL after an error previews normally', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), { code: 'not_public', message: '' }, 422);

      await type(URL_B, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), { ...MEDIA, title: 'Otro' });

      expect(el('preview-error')).toBeNull();
      expect(el('preview-title')?.textContent).toContain('Otro');
    });
  });

  describe('stale requests', () => {
    it('cancels the previous request when a new URL is pasted and ignores its answer', async () => {
      await type(URL_A, 'insertFromPaste');
      const first = http.expectOne('/api/preview');

      await type(URL_B, 'insertFromPaste');
      const second = http.expectOne('/api/preview');

      expect(first.cancelled).toBe(true);
      expect(second.request.body).toEqual({ url: URL_B });
      await answer(second, { ...MEDIA, title: 'El segundo' });
      expect(el('preview-title')?.textContent).toContain('El segundo');
    });

    it('cancels an in-flight request when the user keeps typing', async () => {
      await type(URL_A, 'insertFromPaste');
      const first = http.expectOne('/api/preview');

      await type(URL_A + '&t=5');
      await elapse(DEBOUNCE_MS);

      expect(first.cancelled).toBe(true);
      const second = http.expectOne('/api/preview');
      expect(second.request.body).toEqual({ url: URL_A + '&t=5' });
      await answer(second, MEDIA);
    });

    it('cancels the request and drops the loading state when the field is cleared', async () => {
      await type(URL_A, 'insertFromPaste');
      const first = http.expectOne('/api/preview');

      await type('');
      await elapse(DEBOUNCE_MS);

      expect(first.cancelled).toBe(true);
      expect(el('preview-loading')).toBeNull();
    });
  });

  describe('"Descargar"', () => {
    const JOB = {
      id: 'job1',
      batchId: null,
      playlistIndex: null,
      url: MEDIA.url,
      title: MEDIA.title,
      mode: 'video',
      quality: '720p',
      audioFormat: null,
      status: 'queued',
      progressPercent: 0,
      downloadedBytes: null,
      totalBytes: null,
      speed: null,
      eta: null,
      outputPath: null,
      error: null,
      attempt: 1,
      createdAt: '2026-11-15T12:00:00.000000+00:00',
      startedAt: null,
      finishedAt: null,
    };
    const button = () => el<HTMLButtonElement>('download-button')!;

    beforeEach(async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);
    });

    it('enqueues the previewed video with the selected quality and its title', async () => {
      await pickFormat('format-video-720p');

      expect(button().textContent).toContain('Descargar');
      button().click();
      await settle();

      const req = http.expectOne('/api/jobs');
      expect(req.request.method).toBe('POST');
      expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
      expect(req.request.body).toEqual({
        url: MEDIA.url,
        mode: 'video',
        quality: '720p',
        title: MEDIA.title,
      });
      expect(button().disabled).toBe(true);
      await answer(req, { batchId: null, jobs: [JOB] });

      expect(el('enqueued')?.textContent).toContain('Añadido');
      expect(button().disabled).toBe(false);
      expect(
        TestBed.inject(JobsService)
          .jobs()
          .map((j) => j.id),
      ).toEqual(['job1']);
    });

    const chip = (id: string) =>
      root().querySelector(`[data-testid=preset-apply][data-preset-id=${id}]`) as HTMLElement;

    it('starts on "Mejor video"', () => {
      expect(chip('best-video').getAttribute('aria-pressed')).toBe('true');
      expect(chip('mp3').getAttribute('aria-pressed')).toBe('false');
      expect(el('format-other')?.textContent).toContain('Otro formato');
    });

    it('selects audio from the menu: the chip shows the format and no preset is pressed', async () => {
      await pickFormat('format-audio-m4a');

      expect(fixture.componentInstance.mode()).toBe('audio');
      expect(el('format-other')?.textContent).toContain('M4A');
      expect(chip('best-video').getAttribute('aria-pressed')).toBe('false');
      expect(chip('mp3').getAttribute('aria-pressed')).toBe('false');
    });

    it.each(['mp3', 'm4a', 'opus'])('enqueues audio as %s without a quality', async (format) => {
      await pickFormat(`format-audio-${format}`);

      button().click();
      await settle();

      const req = http.expectOne('/api/jobs');
      expect(req.request.body).toEqual({
        url: MEDIA.url,
        mode: 'audio',
        audioFormat: format,
        title: MEDIA.title,
      });
      await answer(req, {
        batchId: null,
        jobs: [{ ...JOB, mode: 'audio', quality: null, audioFormat: format }],
      });
    });

    it('never sends the audio format of an earlier pick in video mode', async () => {
      await pickFormat('format-audio-opus');
      await pickFormat('format-video-480p');

      button().click();
      await settle();

      expect(http.expectOne('/api/jobs').request.body).toEqual({
        url: MEDIA.url,
        mode: 'video',
        quality: '480p',
        title: MEDIA.title,
      });
    });

    it('keeps mode, quality and format when the next URL is previewed', async () => {
      await pickFormat('format-video-480p');
      await pickFormat('format-audio-opus');

      await type(URL_B, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), { ...MEDIA, url: URL_B, id: 'jNQXAC9IVRw' });

      expect(fixture.componentInstance.mode()).toBe('audio');
      expect(el('format-other')?.textContent).toContain('Opus');
      await openOther();
      expect(el('format-audio-opus')?.getAttribute('aria-checked')).toBe('true');
      el('format-video-480p')!.click();
      await settle();
      expect(el('format-other')?.textContent).toContain('480p');
    });

    it('falls back to "best" when the next video cannot offer the kept quality', async () => {
      await pickFormat('format-video-1080p');

      await type(URL_B, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), {
        ...MEDIA,
        url: URL_B,
        availableQualities: ['best'],
        maxQuality: 'best',
        maxResolution: 240,
      });

      expect(fixture.componentInstance.quality()).toBe('best');
    });

    it('shows a Spanish error when the server refuses', async () => {
      button().click();
      await settle();

      await answer(http.expectOne('/api/jobs'), { code: 'engine_not_ready', message: 'x' }, 409);

      expect(el('enqueue-error')?.textContent).toContain('motor de descarga');
      expect(el('enqueued')).toBeNull();
    });

    it('falls back to the server message for unknown codes', async () => {
      button().click();
      await settle();

      await answer(
        http.expectOne('/api/jobs'),
        { code: 'weird', message: 'Mensaje del servidor' },
        422,
      );

      expect(el('enqueue-error')?.textContent).toContain('Mensaje del servidor');
    });

    it('is disabled (and sends nothing) while the Engine is not ready', async () => {
      engine.engine.set({ ...ENGINE_READY, status: 'installing' } as EngineInfo);
      await settle();

      expect(el('download-button')).toBeNull();
      http.expectNone('/api/jobs');
    });
  });

  describe('presets', () => {
    const chip = (id: string) =>
      root().querySelector(`[data-testid=preset-apply][data-preset-id=${id}]`) as HTMLElement;
    const apply = async (id: string) => {
      chip(id).click();
      await settle();
    };

    beforeEach(async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);
    });

    it('offers "Mejor video" and "MP3" as chips, and no saved formats', () => {
      const chips = Array.from(root().querySelectorAll('[data-testid=preset-apply]'));

      expect(chips.map((c) => c.textContent?.trim())).toEqual(['Mejor video', 'MP3']);
      expect(root().textContent).not.toContain('Guardar como preset');
      expect(root().textContent).not.toContain('Gestionar');
    });

    it('applies "MP3" in one click: mode and format', async () => {
      await apply('mp3');

      expect(fixture.componentInstance.mode()).toBe('audio');
      expect(fixture.componentInstance.audioFormat()).toBe('mp3');
      expect(chip('mp3').getAttribute('aria-pressed')).toBe('true');
      expect(el('format-other')?.textContent).toContain('Otro formato');
    });

    it('applies "Mejor video" in one click, also coming back from audio', async () => {
      await pickFormat('format-video-720p');
      await apply('mp3');
      await apply('best-video');

      expect(fixture.componentInstance.mode()).toBe('video');
      expect(fixture.componentInstance.quality()).toBe('best');
      expect(chip('best-video').getAttribute('aria-pressed')).toBe('true');
    });

    it('falls back to "best" when the video cannot offer the preset quality', async () => {
      await type(URL_B, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), {
        ...MEDIA,
        url: URL_B,
        availableQualities: ['720p'],
        maxQuality: '720p',
      });

      await apply('best-video');

      expect(fixture.componentInstance.quality()).toBe('best');
    });

    it('downloads with what the preset set', async () => {
      await apply('mp3');
      el<HTMLButtonElement>('download-button')!.click();

      const req = http.expectOne('/api/jobs');
      expect(req.request.body).toMatchObject({ mode: 'audio', audioFormat: 'mp3' });
      req.flush({ batchId: null, jobs: [] });
    });
  });

  describe('"Ver playlist completa"', () => {
    const FULL_LIST = 'https://www.youtube.com/playlist?list=PLabc123';

    it('shows only when the preview came from a list', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      expect(el('full-playlist')).toBeNull();
    });

    it('fills the field with the playlist URL and previews it', async () => {
      await type(`${URL_A}&list=PLabc123`, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), { ...MEDIA, playlistUrl: FULL_LIST });

      expect(el('full-playlist')?.textContent).toContain('Ver playlist completa');
      el<HTMLButtonElement>('full-playlist')!.click();
      await settle();

      expect(input().value).toBe(FULL_LIST);
      const req = http.expectOne('/api/preview');
      expect(req.request.body).toEqual({ url: FULL_LIST });
      await answer(req, PLAYLIST);

      expect(el('entries')).not.toBeNull();
    });
  });

  describe('"Otro formato" menu', () => {
    beforeEach(async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);
    });

    it('opens focused on the checked option and moves with the arrow keys', async () => {
      await openOther();
      expect(el('format-other')?.getAttribute('aria-expanded')).toBe('true');
      expect(document.activeElement).toBe(el('format-video-best'));

      root()
        .querySelector('[role=menu]')!
        .dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
      expect(document.activeElement).toBe(el('format-video-1080p')); // 2160p is disabled
    });

    it('closes with Esc and gives the focus back to the chip', async () => {
      document.body.appendChild(root());
      await openOther();

      await pressKey('Escape');

      expect(el('format-menu')).toBeNull();
      expect(document.activeElement).toBe(el('format-other'));
      root().remove();
    });

    it('closes with a click outside', async () => {
      await openOther();

      document.body.click();
      await settle();

      expect(el('format-menu')).toBeNull();
    });
  });

  describe('playlist', () => {
    const LIST_URL = 'https://www.youtube.com/playlist?list=PL59FEE129ADFF2B12';
    const checkboxes = () =>
      Array.from(root().querySelectorAll<HTMLInputElement>('[data-testid=entry-checkbox]'));
    const click = async (testId: string) => {
      el<HTMLButtonElement>(testId)!.click();
      await settle();
    };
    const show = async (playlist = PLAYLIST) => {
      await type(LIST_URL, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), playlist);
    };
    const button = () => el<HTMLButtonElement>('download-button')!;

    it('shows the title, the count and one row per entry', async () => {
      await show();

      expect(el('preview-title')?.textContent).toContain('Test Playlist');
      expect(el('preview-author')?.textContent).toContain('GoogleVoice');
      expect(el('playlist-count')?.textContent).toContain('4 videos');
      expect(el('playlist-truncated')).toBeNull();
      expect(el('preview-duration')).toBeNull();
      expect(
        Array.from(root().querySelectorAll('[data-testid=entry-title]')).map((t) =>
          t.textContent?.trim(),
        ),
      ).toEqual(['The Google Story', 'Parisian Love', 'Video no disponible', 'Cake']);
    });

    it('selects the available entries by default and disables the others with the reason', async () => {
      await show();

      expect(checkboxes().map((c) => c.checked)).toEqual([true, true, false, true]);
      expect(checkboxes().map((c) => c.disabled)).toEqual([false, false, true, false]);
      expect(el('entry-reason')?.textContent).toContain('Video privado o eliminado');
      expect(el('selected-count')?.textContent).toContain('3 / 4');
      expect(button().textContent).toContain('Descargar 3 videos');
    });

    it('warns when the playlist was cut at 500', async () => {
      await show({ ...PLAYLIST, truncated: true });

      expect(el('playlist-truncated')?.textContent).toContain('Mostrando las primeras 500');
    });

    it('deselects and reselects an entry, updating the count and the button', async () => {
      await show();

      checkboxes()[0].click();
      await settle();
      expect(checkboxes().map((c) => c.checked)).toEqual([false, true, false, true]);
      expect(el('selected-count')?.textContent).toContain('2 / 4');
      expect(button().textContent).toContain('Descargar 2 videos');

      checkboxes()[0].click();
      await settle();
      expect(el('selected-count')?.textContent).toContain('3 / 4');
    });

    it('"Ninguno" clears the selection and disables the button; "Seleccionar todo" restores the available ones', async () => {
      await show();

      await click('select-none');
      expect(checkboxes().every((c) => !c.checked)).toBe(true);
      expect(el('selected-count')?.textContent).toContain('0 / 4');
      expect(button().disabled).toBe(true);

      await click('select-all');
      expect(checkboxes().map((c) => c.checked)).toEqual([true, true, false, true]);
      expect(button().disabled).toBe(false);
    });

    it('says "Descargar 1 video" in the singular', async () => {
      await show();
      await click('select-none');

      checkboxes()[1].click();
      await settle();

      expect(button().textContent?.trim()).toBe('Descargar 1 video');
    });

    it('offers every quality, none disabled', async () => {
      await show();

      await openOther();
      const options = menuItems().filter((o) => o.dataset['testid']!.startsWith('format-video'));
      expect(options).toHaveLength(5);
      expect(options.every((o) => !o.disabled)).toBe(true);
      expect(el('preview-max')).toBeNull();
    });

    it('keeps a picked quality that a video would not offer', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);
      await pickFormat('format-video-720p');

      await type(LIST_URL, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), PLAYLIST);

      expect(fixture.componentInstance.quality()).toBe('720p');
      expect(el('format-other')?.textContent).toContain('720p');
    });

    it('applies presets', async () => {
      await show();

      root()
        .querySelector<HTMLButtonElement>('[data-testid=preset-apply][data-preset-id=mp3]')!
        .click();
      await settle();

      expect(fixture.componentInstance.mode()).toBe('audio');
    });

    it('enqueues only the selected entries with the playlist title and the chosen options', async () => {
      await show();
      checkboxes()[1].click(); // drop "Parisian Love"
      await settle();
      await pickFormat('format-audio-m4a');

      button().click();
      await settle();

      const req = http.expectOne('/api/jobs');
      expect(req.request.body).toEqual({
        url: PLAYLIST.url,
        mode: 'audio',
        audioFormat: 'm4a',
        title: 'Test Playlist',
        entries: [
          {
            id: '00000000001',
            url: 'https://www.youtube.com/watch?v=00000000001',
            index: 1,
            title: 'The Google Story',
          },
          {
            id: '00000000004',
            url: 'https://www.youtube.com/watch?v=00000000004',
            index: 4,
            title: 'Cake',
          },
        ],
      });
      await answer(req, { batchId: 'b1', jobs: [] });
      expect(el('enqueued')).not.toBeNull();
    });

    it('never sends entries for a single video', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      el<HTMLButtonElement>('download-button')!.click();
      await settle();

      expect('entries' in http.expectOne('/api/jobs').request.body).toBe(false);
    });

    it('shows a Spanish message when the server rejects the selection', async () => {
      await show();

      button().click();
      await settle();
      await answer(http.expectOne('/api/jobs'), { code: 'invalid_entry', message: 'x' }, 422);

      expect(el('enqueue-error')?.textContent).toContain('no es un enlace de YouTube');
    });

    it('selects everything again for the next playlist', async () => {
      await show();
      await click('select-none');

      await show({ ...PLAYLIST, id: 'other' });

      expect(checkboxes().map((c) => c.checked)).toEqual([true, true, false, true]);
    });
  });
});

describe('looksLikeUrl', () => {
  it.each([
    'https://www.youtube.com/watch?v=abc',
    'http://youtu.be/abc',
    'youtu.be/abc',
    'www.youtube.com/watch?v=abc',
    '  https://example.com  ',
  ])('accepts %s', (value) => expect(looksLikeUrl(value)).toBe(true));

  it.each(['', '   ', 'hola', 'hola mundo', 'https://', 'a b.com', 'https://nodot'])(
    'rejects %j',
    (value) => expect(looksLikeUrl(value)).toBe(false),
  );
});

describe('formatDuration', () => {
  it.each([
    [0, '0:00'],
    [5, '0:05'],
    [19, '0:19'],
    [75, '1:15'],
    [600, '10:00'],
    [3599, '59:59'],
    [3600, '1:00:00'],
    [3725, '1:02:05'],
    [90061, '25:01:01'],
  ])('%i s -> %s', (seconds, text) => expect(formatDuration(seconds)).toBe(text));
});
