import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FakeEventSource } from '../../testing/fake-event-source';
import { appHeaderInterceptor } from '../core/api.interceptor';
import { ENGINE_READY, MEDIA } from '../../testing/fixtures';
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
    it('disables the field and says why', async () => {
      engine.engine.set({ ...ENGINE_READY, status: 'installing' } as EngineInfo);
      await settle();

      expect(input().disabled).toBe(true);
      expect(el('url-hint')?.textContent).toContain('motor de descarga');
    });

    it('enables it once the Engine is ready', async () => {
      expect(input().disabled).toBe(false);
      expect(el('url-hint')).toBeNull();
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

    it('shows title, author, duration, thumbnail and the maximum resolution', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), { ...MEDIA, duration: 3725 });

      expect(el('preview-title')?.textContent).toContain('Un Short vertical');
      expect(el('preview-author')?.textContent).toContain('YouTube');
      expect(el('preview-duration')?.textContent).toContain('1:02:05');
      expect(el('preview-max')?.textContent).toContain('1080p');
      expect(el<HTMLImageElement>('preview-thumbnail')?.src).toBe(MEDIA.thumbnail);
    });

    it('lists every Quality and disables those above the maximum', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      const options = Array.from(
        root().querySelectorAll<HTMLOptionElement>('[data-testid=quality-select] option'),
      );
      expect(options.map((o) => [o.value, o.disabled])).toEqual([
        ['best', false],
        ['2160p', true],
        ['1080p', false],
        ['720p', false],
        ['480p', false],
      ]);
      expect(options[0].textContent).toContain('Mejor disponible');
      expect(options[1].textContent).toContain('VLC');
      expect(options[0].selected).toBe(true);
    });

    it('offers only "best" for a low resolution video', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), {
        ...MEDIA,
        availableQualities: ['best'],
        maxQuality: 'best',
        maxResolution: 240,
      });

      const enabled = Array.from(
        root().querySelectorAll<HTMLOptionElement>('[data-testid=quality-select] option'),
      ).filter((o) => !o.disabled);
      expect(enabled.map((o) => o.value)).toEqual(['best']);
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

    it('keeps the Quality the user picks', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      const select = el<HTMLSelectElement>('quality-select')!;
      select.value = '720p';
      select.dispatchEvent(new Event('change'));
      await settle();

      expect(fixture.componentInstance.quality()).toBe('720p');
    });

    it('shows the hint next to 2160p and a notice while it is selected', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), {
        ...MEDIA,
        availableQualities: ['best', '2160p', '1080p'],
        maxQuality: '2160p',
      });

      expect(el('quality-2160-hint')).toBeNull();
      const select = el<HTMLSelectElement>('quality-select')!;
      select.value = '2160p';
      select.dispatchEvent(new Event('change'));
      await settle();

      expect(el('quality-2160-hint')?.textContent).toContain('VLC');
      select.value = '720p';
      select.dispatchEvent(new Event('change'));
      await settle();
      expect(el('quality-2160-hint')).toBeNull();
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
      ['playlist_unsupported', 422, 'playlists y canales todavía no'],
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
      const select = el<HTMLSelectElement>('quality-select')!;
      select.value = '720p';
      select.dispatchEvent(new Event('change'));
      await settle();

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

    const pickMode = async (mode: 'video' | 'audio') => {
      el<HTMLInputElement>(`mode-${mode}`)!.click();
      await settle();
    };
    const pick = async (testId: string, value: string) => {
      const select = el<HTMLSelectElement>(testId)!;
      select.value = value;
      select.dispatchEvent(new Event('change'));
      await settle();
    };

    it('starts in video mode with the quality selector and no audio selector', () => {
      expect(el<HTMLInputElement>('mode-video')!.checked).toBe(true);
      expect(el('quality-select')).not.toBeNull();
      expect(el('audio-format-select')).toBeNull();
    });

    it('switches to audio: the AudioFormat selector replaces the Quality one', async () => {
      await pickMode('audio');

      expect(el<HTMLInputElement>('mode-audio')!.checked).toBe(true);
      expect(el('quality-select')).toBeNull();
      const options = Array.from(
        root().querySelectorAll<HTMLOptionElement>('[data-testid=audio-format-select] option'),
      );
      expect(options.map((o) => o.value).sort()).toEqual(['m4a', 'mp3', 'opus']);
      expect(options.every((o) => !o.disabled)).toBe(true);
      expect(el<HTMLSelectElement>('audio-format-select')!.value).toBe('m4a');
    });

    it.each(['mp3', 'm4a', 'opus'])('enqueues audio as %s without a quality', async (format) => {
      await pickMode('audio');
      await pick('audio-format-select', format);

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
      await pickMode('audio');
      await pick('audio-format-select', 'opus');
      await pickMode('video');
      await pick('quality-select', '480p');

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
      await pick('quality-select', '480p');
      await pickMode('audio');
      await pick('audio-format-select', 'mp3');

      await type(URL_B, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), { ...MEDIA, url: URL_B, id: 'jNQXAC9IVRw' });

      expect(el<HTMLInputElement>('mode-audio')!.checked).toBe(true);
      expect(el<HTMLSelectElement>('audio-format-select')!.value).toBe('mp3');
      await pickMode('video');
      expect(el<HTMLSelectElement>('quality-select')!.value).toBe('480p');
    });

    it('falls back to "best" when the next video cannot offer the kept quality', async () => {
      await pick('quality-select', '1080p');

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

  describe('"Ver playlist completa"', () => {
    const PLAYLIST = 'https://www.youtube.com/playlist?list=PLabc123';

    it('shows only when the preview came from a list', async () => {
      await type(URL_A, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), MEDIA);

      expect(el('full-playlist')).toBeNull();
    });

    it('fills the field with the playlist URL and previews it', async () => {
      await type(`${URL_A}&list=PLabc123`, 'insertFromPaste');
      await answer(http.expectOne('/api/preview'), { ...MEDIA, playlistUrl: PLAYLIST });

      expect(el('full-playlist')?.textContent).toContain('Ver playlist completa');
      el<HTMLButtonElement>('full-playlist')!.click();
      await settle();

      expect(input().value).toBe(PLAYLIST);
      const req = http.expectOne('/api/preview');
      expect(req.request.body).toEqual({ url: PLAYLIST });
      await answer(req, { code: 'playlist_unsupported', message: '' }, 422);
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
