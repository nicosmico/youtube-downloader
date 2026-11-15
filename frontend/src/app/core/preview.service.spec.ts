import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { appHeaderInterceptor } from './api.interceptor';
import { MediaPreview, PreviewError, PreviewService } from './preview.service';

export const MEDIA: MediaPreview = {
  kind: 'video',
  id: 'Jt5fgKBqZSY',
  url: 'https://www.youtube.com/watch?v=Jt5fgKBqZSY',
  title: 'Un Short vertical',
  thumbnail: 'https://i.ytimg.com/vi/Jt5fgKBqZSY/maxresdefault.jpg',
  duration: 32,
  author: 'YouTube',
  availableQualities: ['best', '1080p', '720p', '480p'],
  maxQuality: '1080p',
  maxResolution: 1080,
};

describe('PreviewService', () => {
  let service: PreviewService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(PreviewService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  const failure = (status: number, body: object | string): PreviewError => {
    let caught: unknown;
    service.fetch('https://youtu.be/x').subscribe({ error: (e: unknown) => (caught = e) });
    http.expectOne('/api/preview').flush(body, { status, statusText: 'x' });
    return caught as PreviewError;
  };

  it('posts the URL with the app header and returns the preview', () => {
    let result: MediaPreview | undefined;
    service.fetch('https://youtu.be/Jt5fgKBqZSY').subscribe((media) => (result = media));

    const req = http.expectOne('/api/preview');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ url: 'https://youtu.be/Jt5fgKBqZSY' });
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush(MEDIA);

    expect(result).toEqual(MEDIA);
  });

  it('turns an API error into a PreviewError with its code', () => {
    const error = failure(422, { code: 'not_public', message: 'No es público' });

    expect(error).toBeInstanceOf(PreviewError);
    expect(error.code).toBe('not_public');
    expect(error.message).toBe('No es público');
  });

  it('keeps engine_not_ready distinguishable', () => {
    expect(failure(409, { code: 'engine_not_ready', message: 'x' }).code).toBe('engine_not_ready');
  });

  it('maps an unknown code or a non-JSON body to "unknown"', () => {
    expect(failure(500, { code: 'something_new', message: 'x' }).code).toBe('unknown');
    expect(failure(502, '<html>bad gateway</html>').code).toBe('unknown');
  });

  it('maps a request that never reached the server to "network"', () => {
    let caught: PreviewError | undefined;
    service.fetch('https://youtu.be/x').subscribe({ error: (e: PreviewError) => (caught = e) });
    http.expectOne('/api/preview').error(new ProgressEvent('error'));

    expect(caught?.code).toBe('network');
  });

  it('cancels the HTTP request when unsubscribed', () => {
    const subscription = service.fetch('https://youtu.be/x').subscribe();
    const req = http.expectOne('/api/preview');

    subscription.unsubscribe();

    expect(req.cancelled).toBe(true);
  });
});
