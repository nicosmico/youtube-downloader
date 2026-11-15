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
        lastUpdateCheck: null,
        updateMessage: null,
      },
      port: 1,
    };
    req.flush(body);

    expect(result).toEqual(body);
  });

  it('sends the app header when requesting shutdown', () => {
    service.shutdown().subscribe();

    const req = http.expectOne('/api/system/shutdown');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ status: 'shutting_down' });
  });
});
