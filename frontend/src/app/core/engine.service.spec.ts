import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { FakeEventSource } from '../../testing/fake-event-source';
import { appHeaderInterceptor } from './api.interceptor';
import { EVENT_SOURCE_FACTORY, EngineInfo, EngineService } from './engine.service';

export const ENGINE_READY: EngineInfo = {
  status: 'ready',
  message: null,
  versions: { ytDlp: '2026.10.26', ffmpeg: '9.0.2', ffprobe: '9.0.2', deno: '2.9.8' },
  updating: false,
  updatePending: false,
  lastUpdateCheck: null,
  updateMessage: null,
};

describe('EngineService', () => {
  let service: EngineService;
  let http: HttpTestingController;

  beforeEach(() => {
    FakeEventSource.reset();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    });
    service = TestBed.inject(EngineService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('is not ready until the server says so', () => {
    expect(service.engineReady()).toBe(false);
    service.engine.set({ ...ENGINE_READY, status: 'installing' });
    expect(service.engineReady()).toBe(false);
    service.engine.set(ENGINE_READY);
    expect(service.engineReady()).toBe(true);
  });

  it('opens one event stream and rehydrates from the REST endpoint on every connect', () => {
    service.connect();
    service.connect();
    expect(FakeEventSource.instances.map((s) => s.url)).toEqual(['/api/events']);

    FakeEventSource.instances[0].open();
    http.expectOne('/api/system/engine').flush({ ...ENGINE_READY, status: 'installing' });
    expect(service.engine()?.status).toBe('installing');

    // the connection dropped and came back while the Engine became ready
    FakeEventSource.instances[0].open();
    http.expectOne('/api/system/engine').flush(ENGINE_READY);
    expect(service.engineReady()).toBe(true);
  });

  it('applies engine.updated events', () => {
    service.connect();
    FakeEventSource.instances[0].emit('engine.updated', { ...ENGINE_READY, status: 'error' });

    expect(service.engine()?.status).toBe('error');
    expect(service.engineReady()).toBe(false);
  });

  it('posts install and update with the app header', () => {
    service.install();
    const install = http.expectOne('/api/system/engine/install');
    expect(install.request.method).toBe('POST');
    expect(install.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    install.flush({ ...ENGINE_READY, status: 'installing' });
    expect(service.engine()?.status).toBe('installing');

    service.update();
    http.expectOne('/api/system/engine/update').flush(ENGINE_READY);
  });

  it('flags a rejected command', () => {
    service.update();
    http
      .expectOne('/api/system/engine/update')
      .flush({ code: 'engine_busy', message: 'x' }, { status: 409, statusText: 'Conflict' });

    expect(service.actionError()).toBe(true);
  });

  it('closes the stream when destroyed', () => {
    service.connect();
    service.ngOnDestroy();

    expect(FakeEventSource.instances[0].closed).toBe(true);
  });
});
