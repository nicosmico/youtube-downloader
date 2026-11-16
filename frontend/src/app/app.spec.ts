import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App } from './app';
import { FakeEventSource } from '../testing/fake-event-source';
import { appHeaderInterceptor } from './core/api.interceptor';
import { EVENT_SOURCE_FACTORY, EngineInfo } from './core/engine.service';
import { SystemService } from './core/system.service';
import { flushRehydration } from '../testing/rehydration';

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
  updatePending: false,
  lastUpdateCheck: null,
  updateMessage: null,
};

describe('App', () => {
  let fixture: ComponentFixture<App>;
  let http: HttpTestingController;

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const el = (selector: string) =>
    (fixture.nativeElement as HTMLElement).querySelector(selector) as HTMLButtonElement | null;
  const button = () => el('[data-testid=shutdown]') as HTMLButtonElement;
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

  const openChip = async () => {
    el('[data-testid=engine-chip]')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const chipText = () => el('[data-testid=engine-chip]')?.textContent ?? '';
  const popover = () => el('[data-testid=engine-popover]');
  const press = async (key: string) => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key }));
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const openGear = async () => {
    el('[data-testid=gear-menu]')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
  };

  it('has the brand on the left and no text field in the top bar', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();
    fixture.detectChanges();

    const header = el('header')!;
    expect(header.textContent).toContain('YouTube Downloader');
    expect(header.querySelector('[data-testid=brand-icon]')).not.toBeNull();
    expect(header.querySelector('input, textarea, [contenteditable]')).toBeNull();
  });

  it('shows an amber "Motor no instalado" chip before the Engine reports anything', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();
    stream().open();
    http.expectOne('/api/system/engine').flush({ ...ENGINE, status: 'missing' });
    flushRehydration(http);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(chipText()).toContain('Motor no instalado');
    expect(el('[data-testid=engine-chip] span')?.className).toContain('bg-amber-500');
    await openChip();
    expect(el('[data-testid=engine-update]')).toBeNull();
    expect(el('[data-testid=engine-retry]')).toBeNull();
  });

  it('shows "Instalando…" live, then a green "Motor listo" with versions in the popover', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({ status: 'installing' });
    expect(chipText()).toContain('Instalando…');

    await pushEngine({});
    expect(chipText()).toContain('Motor listo');
    expect(el('[data-testid=engine-chip] span')?.className).toContain('bg-green-600');
    expect(popover()).toBeNull();

    await openChip();
    expect(popover()?.textContent).toContain('2026.10.26');
    expect(popover()?.textContent).toContain('ffmpeg');
    expect(popover()?.textContent).toContain('Deno');
    expect(popover()?.textContent).toContain('v0.1.0 · 4321');
    expect(el('[data-testid=engine-update]')?.textContent).toContain('Actualizar yt-dlp');
  });

  it('shows a red chip with the error and "Reintentar", which asks the server to install again', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({ status: 'error', message: 'No se pudo descargar deno: sin conexión.' });

    expect(chipText()).toContain('Motor con error');
    expect(el('[data-testid=engine-chip] span')?.className).toContain('bg-accent');
    await openChip();
    expect(el('[data-testid=engine-error]')?.textContent).toContain('sin conexión');
    el('[data-testid=engine-retry]')?.click();

    const req = http.expectOne('/api/system/engine/install');
    expect(req.request.method).toBe('POST');
    req.flush({ ...ENGINE, status: 'installing', versions: {} });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(chipText()).toContain('Instalando…');
    expect(el('[data-testid=engine-retry]')).toBeNull();
  });

  it('"Actualizar yt-dlp" posts the update and is disabled while it runs', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({});
    await openChip();
    el('[data-testid=engine-update]')?.click();

    http.expectOne('/api/system/engine/update').flush({ ...ENGINE, updating: true });
    await fixture.whenStable();
    fixture.detectChanges();

    const update = el('[data-testid=engine-update]') as HTMLButtonElement;
    expect(update.disabled).toBe(true);
    expect(update.textContent).toContain('Actualizando…');
    expect(chipText()).toContain('Actualizando…');
  });

  it('shows an amber "Actualización pendiente" until the active downloads finish', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({});
    await openChip();
    expect(el('[data-testid=engine-update-pending]')).toBeNull();

    await pushEngine({ updatePending: true });

    expect(chipText()).toContain('Actualización pendiente');
    expect(el('[data-testid=engine-chip] span')?.className).toContain('bg-amber-500');
    expect(el('[data-testid=engine-update-pending]')?.textContent).toContain(
      'se aplicará al terminar las descargas en curso',
    );
    expect((el('[data-testid=engine-update]') as HTMLButtonElement).disabled).toBe(true);

    // the swap happens: the new version is shown and the notice goes away
    await pushEngine({ updatePending: false, updating: true });
    expect(el('[data-testid=engine-update-pending]')).toBeNull();
    await pushEngine({ versions: { ...ENGINE.versions, ytDlp: '2026.11.30' } });
    expect(popover()?.textContent).toContain('2026.11.30');
    expect(chipText()).toContain('Motor listo');
    expect((el('[data-testid=engine-update]') as HTMLButtonElement).disabled).toBe(false);
  });

  it('keeps the update pending when the server accepts it with downloads running', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({});
    await openChip();
    el('[data-testid=engine-update]')?.click();

    http.expectOne('/api/system/engine/update').flush({ ...ENGINE, updatePending: true });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el('[data-testid=engine-update-pending]')).not.toBeNull();
    expect(popover()?.querySelector('[role=alert]')).toBeNull();
  });

  it('shows why a yt-dlp update failed', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({ updateMessage: 'sin conexión' });
    await openChip();

    expect(popover()?.textContent).toContain('No se pudo actualizar yt-dlp: sin conexión');
  });

  it('closes the Engine popover with Esc (back on the chip) and with a click outside', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({});
    await openChip();
    expect(el('[data-testid=engine-chip]')?.getAttribute('aria-expanded')).toBe('true');

    await press('Escape');
    expect(popover()).toBeNull();
    expect(document.activeElement).toBe(el('[data-testid=engine-chip]'));

    await openChip();
    document.body.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(popover()).toBeNull();
  });

  it('shows an error when the server cannot be reached', async () => {
    http.expectOne('/api/health').error(new ProgressEvent('error'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(chipText()).toContain('Sin conexión');
    await openChip();
    expect(popover()?.textContent).toContain('No se pudo contactar con el servidor local.');
  });

  it('opens the gear menu with theme, Registros and Cerrar aplicación; Esc closes it', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();
    await openGear();

    const menu = el('[role=menu]')!;
    expect(menu.textContent).toContain('Sistema');
    expect(menu.textContent).toContain('Claro');
    expect(menu.textContent).toContain('Oscuro');
    expect(menu.textContent).toContain('Registros');
    expect(menu.textContent).toContain('Cerrar aplicación');
    expect(document.activeElement).toBe(el('[data-testid=theme-system]'));

    await press('Escape');
    expect(el('[role=menu]')).toBeNull();
    expect(document.activeElement).toBe(el('[data-testid=gear-menu]'));
  });

  it('chooses the theme from the gear menu and from the theme button', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();
    localStorage.clear();
    await openGear();

    el('[data-testid=theme-dark]')!.click();
    fixture.detectChanges();
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(el('[data-testid=theme-dark]')?.getAttribute('aria-checked')).toBe('true');
    expect(localStorage.getItem('theme')).toBe('dark');

    el('[data-testid=theme-toggle]')!.click();
    fixture.detectChanges();
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(localStorage.getItem('theme')).toBe('light');
    document.documentElement.classList.remove('dark');
  });

  it('opens Registros in a side panel, which Esc closes and gives the focus back', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();
    await openGear();

    el('[data-testid=open-logs]')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
    http.expectOne((r) => r.url === '/api/logs').flush({ lines: [] });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el('[data-testid=logs-panel]')).not.toBeNull();
    expect(el('[role=menu]')).toBeNull();

    await press('Escape');
    expect(el('[data-testid=logs-panel]')).toBeNull();
    expect(document.activeElement).toBe(el('[data-testid=gear-menu]'));
  });

  it('shows the closed state after "Cerrar aplicación"', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();

    await openGear();
    expect(button().textContent).toContain('Cerrar aplicación');
    button().click();

    const req = http.expectOne('/api/system/shutdown');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ status: 'shutting_down' });
    await fixture.whenStable();

    expect(text()).toContain('La aplicación se cerró');
    expect(el('button')).toBeNull();
  });
  it('shows the idle-closed screen when the server announces an idle shutdown', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();

    stream().emit('shutdown', { reason: 'idle' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el('[data-testid=closed-title]')?.textContent).toContain(
      'La aplicación se cerró por inactividad',
    );
    expect(text()).toContain('Ya puedes cerrar esta pestaña');
    expect(el('button')).toBeNull();
    expect(stream().closed).toBe(true); // the browser must not keep reconnecting
  });

  it('shows the plain closed screen for other shutdown reasons', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();

    stream().emit('shutdown', { reason: 'user' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el('[data-testid=closed-title]')?.textContent).toContain('La aplicación se cerró');
    expect(el('[data-testid=closed-title]')?.textContent).not.toContain('inactividad');
  });

  it('labels the reveal button from the platform that /api/health reports', async () => {
    http.expectOne('/api/health').flush({ ...HEALTH, platform: 'darwin' });
    await fixture.whenStable();

    expect(TestBed.inject(SystemService).platform()).toBe('darwin');
  });
});
