import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App } from './app';
import { FakeEventSource } from '../testing/fake-event-source';
import { appHeaderInterceptor } from './core/api.interceptor';
import { EVENT_SOURCE_FACTORY, EngineInfo } from './core/engine.service';

const HEALTH = {
  app: 'youtube-downloader',
  version: '0.1.0',
  engine: { status: 'missing' },
  port: 4321,
};

const ENGINE: EngineInfo = {
  status: 'ready',
  message: null,
  versions: { ytDlp: '2026.10.26', ffmpeg: '9.0.2', ffprobe: '9.0.2', deno: '2.9.8' },
  updating: false,
  lastUpdateCheck: null,
  updateMessage: null,
};

describe('App', () => {
  let fixture: ComponentFixture<App>;
  let http: HttpTestingController;

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const el = (selector: string) =>
    (fixture.nativeElement as HTMLElement).querySelector(selector) as HTMLButtonElement | null;
  const button = () => el('button.danger') as HTMLButtonElement;
  const stream = () => FakeEventSource.instances[0];
  const pushEngine = async (engine: Partial<EngineInfo>) => {
    stream().emit('engine.updated', { ...ENGINE, ...engine });
    await fixture.whenStable();
    fixture.detectChanges();
  };

  beforeEach(async () => {
    FakeEventSource.reset();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(App);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('shows the title, the port and "No instalado" before the Engine reports anything', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();
    stream().open();
    http.expectOne('/api/system/engine').flush({ ...ENGINE, status: 'missing' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(text()).toContain('YouTube Downloader');
    expect(text()).toContain('No instalado');
    expect(text()).toContain('4321');
    expect(el('[data-testid=engine-update]')).toBeNull();
    expect(el('[data-testid=engine-retry]')).toBeNull();
  });

  it('shows "Instalando…" live, then "Listo" with the versions and the update button', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({ status: 'installing' });
    expect(text()).toContain('Instalando…');

    await pushEngine({});
    expect(text()).toContain('Listo');
    expect(text()).toContain('yt-dlp 2026.10.26');
    expect(text()).toContain('ffmpeg 9.0.2');
    expect(text()).toContain('Deno 2.9.8');
    expect(el('[data-testid=engine-update]')?.textContent).toContain('Actualizar yt-dlp');
  });

  it('shows the error and "Reintentar", which asks the server to install again', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({ status: 'error', message: 'No se pudo descargar deno: sin conexión.' });

    expect(text()).toContain('Error');
    expect(el('[data-testid=engine-error]')?.textContent).toContain('sin conexión');
    el('[data-testid=engine-retry]')?.click();

    const req = http.expectOne('/api/system/engine/install');
    expect(req.request.method).toBe('POST');
    req.flush({ ...ENGINE, status: 'installing', versions: {} });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(text()).toContain('Instalando…');
    expect(el('[data-testid=engine-retry]')).toBeNull();
  });

  it('"Actualizar yt-dlp" posts the update and is disabled while it runs', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({});
    el('[data-testid=engine-update]')?.click();

    http.expectOne('/api/system/engine/update').flush({ ...ENGINE, updating: true });
    await fixture.whenStable();
    fixture.detectChanges();

    const update = el('[data-testid=engine-update]') as HTMLButtonElement;
    expect(update.disabled).toBe(true);
    expect(update.textContent).toContain('Actualizando…');
  });

  it('shows why a yt-dlp update failed', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({ updateMessage: 'sin conexión' });

    expect(text()).toContain('No se pudo actualizar yt-dlp: sin conexión');
  });

  it('shows an error when the server cannot be reached', async () => {
    http.expectOne('/api/health').error(new ProgressEvent('error'));
    await fixture.whenStable();

    expect(text()).toContain('No se pudo contactar con el servidor local.');
  });

  it('shows the closed state after "Cerrar aplicación"', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();

    expect(button().textContent).toContain('Cerrar aplicación');
    button().click();

    const req = http.expectOne('/api/system/shutdown');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ status: 'shutting_down' });
    await fixture.whenStable();

    expect(text()).toContain('La aplicación se cerró');
    expect(el('button')).toBeNull();
  });
});
