import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ENGINE_READY } from '../../testing/fixtures';
import { appHeaderInterceptor } from '../core/api.interceptor';
import { EngineService } from '../core/engine.service';
import { ERROR_LOG_CLOCK, ErrorLogService } from '../core/error-log.service';
import { SystemService } from '../core/system.service';
import { Logs } from './logs';

describe('Logs', () => {
  let fixture: ComponentFixture<Logs>;
  let http: HttpTestingController;

  const root = () => fixture.nativeElement as HTMLElement;
  const el = <T extends HTMLElement = HTMLElement>(id: string) =>
    root().querySelector<T>(`[data-testid=${id}]`);
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const click = async (id: string) => {
    el(id)!.click();
    await settle();
  };
  const logsUrl =
    (requests: boolean) => (req: { url: string; params: { get(k: string): string | null } }) =>
      req.url === '/api/logs' &&
      req.params.get('lines') === '500' &&
      req.params.get('requests') === String(requests);
  const answer = async (lines: string[], requests = false) => {
    http.expectOne(logsUrl(requests)).flush({ lines });
    await settle();
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Logs],
      providers: [
        { provide: ERROR_LOG_CLOCK, useValue: () => new Date('2026-11-15T12:30:00.000Z') },
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Logs);
    await settle();
  });

  afterEach(() => http.verify());

  it('is collapsed by default and asks the server for nothing', () => {
    expect(el('logs-toggle')?.getAttribute('aria-expanded')).toBe('false');
    expect(el('logs-body')).toBeNull();
    http.expectNone('/api/logs');
  });

  it('loads the log when opened and shows the lines', async () => {
    await click('logs-toggle');
    await answer(['one', 'two']);

    expect(el('logs-toggle')?.getAttribute('aria-expanded')).toBe('true');
    expect(el('logs-server')?.textContent).toBe('one\ntwo');
    expect(el('logs-frontend-empty')).not.toBeNull();
  });

  it('does not ask again when closed and does when reopened', async () => {
    await click('logs-toggle');
    await answer(['one']);
    await click('logs-toggle');
    expect(el('logs-body')).toBeNull();

    await click('logs-toggle');
    await answer(['one', 'two']);

    expect(el('logs-server')?.textContent).toBe('one\ntwo');
  });

  it('reloads only on "Actualizar"', async () => {
    await click('logs-toggle');
    await answer(['one']);

    await click('logs-refresh');
    await answer(['one', 'two']);

    expect(el('logs-server')?.textContent).toBe('one\ntwo');
  });

  it('reloads with requests when the toggle is switched', async () => {
    await click('logs-toggle');
    await answer(['one']);

    await click('logs-requests');
    await answer(['one', 'GET /api/jobs'], true);

    expect(el('logs-server')?.textContent).toContain('GET /api/jobs');
  });

  it('says so when the server log cannot be read, and when it is empty', async () => {
    await click('logs-toggle');
    http.expectOne(logsUrl(false)).flush({}, { status: 500, statusText: 'Error' });
    await settle();
    expect(el('logs-load-error')?.textContent).toContain('No se pudo leer');

    await click('logs-refresh');
    await answer([]);
    expect(el('logs-load-error')).toBeNull();
    expect(el('logs-server-empty')).not.toBeNull();
  });

  it('shows the errors captured in this tab', async () => {
    TestBed.inject(ErrorLogService).record('http', 'GET /api/jobs -> 500');
    await click('logs-toggle');
    await answer([]);

    expect(el('logs-frontend')?.textContent).toBe(
      '2026-11-15T12:30:00.000Z [http] GET /api/jobs -> 500',
    );
  });

  describe('report', () => {
    let written: string[];

    beforeEach(async () => {
      written = [];
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: async (text: string) => void written.push(text) },
      });
      TestBed.inject(SystemService).version.set('0.1.1');
      TestBed.inject(SystemService).platform.set('darwin');
      TestBed.inject(EngineService).engine.set(ENGINE_READY);
      TestBed.inject(ErrorLogService).record('js', 'TypeError: boom');
      await click('logs-toggle');
      await answer(['2026 INFO app: hola']);
    });

    it('copies the header and both sources', async () => {
      await click('logs-copy');

      expect(written).toHaveLength(1);
      expect(written[0]).toContain('Versión de la app: 0.1.1');
      expect(written[0]).toContain('Plataforma: darwin');
      expect(written[0]).toContain('yt-dlp 2026.10.26');
      expect(written[0]).toContain('Deno 2.9.8');
      expect(written[0]).toContain('2026 INFO app: hola');
      expect(written[0]).toContain('[js] TypeError: boom');
      expect(written[0]).toContain('sin peticiones');
      expect(el('logs-message')?.textContent).toContain('Copiado');
    });

    it('says when copying is not possible', async () => {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: () => Promise.reject(new Error('denied')) },
      });

      await click('logs-copy');

      expect(el('logs-message')?.textContent).toContain('No se pudo copiar');
    });

    it('downloads the same report as a .txt file', async () => {
      let blob: Blob | null = null;
      URL.createObjectURL = (b: Blob | MediaSource) => {
        blob = b as Blob;
        return 'blob:test';
      };
      URL.revokeObjectURL = () => undefined;
      const names: string[] = [];
      vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
        this: HTMLAnchorElement,
      ) {
        names.push(this.download);
      });

      await click('logs-download');

      expect(names).toEqual(['registros-youtube-downloader.txt']);
      const text = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.readAsText(blob!);
      });
      expect(text).toContain('Versión de la app: 0.1.1');
      expect(text).toContain('2026 INFO app: hola');
      expect(text).toContain('[js] TypeError: boom');
    });
  });
});
