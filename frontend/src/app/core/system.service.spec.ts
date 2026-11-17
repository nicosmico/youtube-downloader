import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { appHeaderInterceptor } from './api.interceptor';
import { SystemService } from './system.service';

describe('SystemService', () => {
  let service: SystemService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(SystemService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('reads the health payload without the app header on GET', () => {
    let result: unknown;
    service.health().subscribe((h) => (result = h));

    const req = http.expectOne('/api/health');
    expect(req.request.headers.has('X-Requested-With')).toBe(false);
    const body = {
      app: 'youtube-downloader',
      version: '0.1.0',
      engine: {
        status: 'missing',
        message: null,
        versions: { ytDlp: null, ffmpeg: null, ffprobe: null, deno: null },
        updating: false,
        updatePending: false,
        lastUpdateCheck: null,
        updateMessage: null,
      },
      port: 1,
    };
    req.flush(body);

    expect(result).toEqual(body);
  });

  it('does not store the folder when the dialog is canceled', () => {
    let result: unknown;
    service.chooseDownloadDir().subscribe((r) => (result = r));

    const req = http.expectOne('/api/settings/download-dir/choose');
    expect(req.request.method).toBe('POST');
    req.flush({ canceled: true });

    expect(result).toEqual({ canceled: true });
    expect(service.downloadDir()).toBeNull();
  });

  it('stores the chosen folder and the one after a reset', () => {
    const dir = { path: '/a', display: '/a', isDefault: false, available: true };
    service.chooseDownloadDir().subscribe();
    http.expectOne('/api/settings/download-dir/choose').flush(dir);
    expect(service.downloadDir()).toEqual(dir);

    const def = { path: '/h/Downloads', display: '~/Downloads', isDefault: true, available: true };
    service.resetDownloadDir().subscribe();
    const req = http.expectOne('/api/settings/download-dir');
    expect(req.request.method).toBe('DELETE');
    req.flush(def);
    expect(service.downloadDir()).toEqual(def);
  });

  it('sends the app header when requesting shutdown', () => {
    service.shutdown().subscribe();

    const req = http.expectOne('/api/system/shutdown');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ status: 'shutting_down' });
  });
});
