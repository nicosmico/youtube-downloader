import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App } from './app';
import { FakeEventSource } from '../testing/fake-event-source';
import { appHeaderInterceptor } from './core/api.interceptor';
import { EVENT_SOURCE_FACTORY, EngineInfo } from './core/engine.service';
import { DownloadDir, SystemService } from './core/system.service';
import { flushRehydration } from '../testing/rehydration';

const HEALTH = {
  app: 'youtube-downloader',
  version: '0.1.0',
  engine: { status: 'missing' },
  port: 4321,
};

const DIR: DownloadDir = {
  path: '/Users/ana/Downloads',
  display: '~/Downloads',
  isDefault: true,
  available: true,
};
const CUSTOM_DIR: DownloadDir = {
  path: '/Volumes/Disco/Música',
  display: '/Volumes/Disco/Música',
  isDefault: false,
  available: true,
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

  it('keeps the brand name and the chip label for screen readers on narrow windows', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await pushEngine({});

    expect(el('header h1')?.className).toContain('max-sm:sr-only');
    expect(el('[data-testid=engine-status]')?.className).toContain('max-sm:sr-only');
    expect(el('[data-testid=engine-chip]')?.getAttribute('aria-label')).toContain('Motor listo');
  });

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
    http.expectOne('/api/settings/download-dir').flush(DIR);
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

  const UPDATE = {
    version: '0.2.2',
    url: 'https://github.com/nicosmico/youtube-downloader/releases/tag/v0.2.2',
  };
  const updateChip = () => el('[data-testid=update-chip]') as HTMLAnchorElement | null;

  it('shows no update chip when /api/health reports no update', async () => {
    http.expectOne('/api/health').flush({ ...HEALTH, update: null });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(updateChip()).toBeNull();
  });

  it('shows a link chip with the new version next to the Engine chip', async () => {
    http.expectOne('/api/health').flush({ ...HEALTH, update: UPDATE });
    await fixture.whenStable();
    fixture.detectChanges();

    const chip = updateChip()!;
    expect(chip.textContent).toContain('v0.2.2');
    expect(chip.getAttribute('href')).toBe(UPDATE.url);
    expect(chip.getAttribute('target')).toBe('_blank');
    expect(chip.getAttribute('rel')).toBe('noopener');
    expect(chip.getAttribute('aria-label')).toBe('Hay una versión nueva: 0.2.2');
    expect(chip.getAttribute('title')).toBe('Hay una versión nueva: 0.2.2');
    expect(chip.querySelector('svg')).not.toBeNull();
    expect(chip.querySelector('span')?.className).toContain('max-sm:sr-only');
    expect(chip.previousElementSibling).toBe(el('app-engine-chip'));
  });

  it('shows the chip when the app.update event arrives, without reloading', async () => {
    http.expectOne('/api/health').flush({ ...HEALTH, update: null });
    await fixture.whenStable();
    expect(updateChip()).toBeNull();

    stream().emit('app.update', UPDATE);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(updateChip()?.getAttribute('href')).toBe(UPDATE.url);
    expect(updateChip()?.textContent).toContain('v0.2.2');
  });

  it('shows the installed version as a quiet line after Cerrar aplicación, not as a menu item', async () => {
    http.expectOne('/api/health').flush({ ...HEALTH, version: '0.2.1' });
    await fixture.whenStable();
    await openGear();

    const menu = el('[role=menu]')!;
    const line = el('[data-testid=app-version-line]')!;
    expect(line.textContent?.trim()).toBe('Versión 0.2.1');
    expect(line.getAttribute('role')).toBeNull();
    expect(menu.lastElementChild).toBe(line);
    expect(menu.querySelectorAll('[role^=menuitem]')).not.toContain(line);
    expect(line.previousElementSibling).toBe(el('[data-testid=shutdown]'));
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

  describe('download folder in the gear menu', () => {
    const dirEl = (id: string) => el(`[data-testid=download-dir-${id}]`);
    const change = () => dirEl('change') as HTMLButtonElement;
    const settle = async () => {
      await fixture.whenStable();
      fixture.detectChanges();
    };
    const load = async (dir: DownloadDir = DIR) => {
      http.expectOne('/api/health').flush(HEALTH);
      stream().open();
      http.expectOne('/api/system/engine').flush({ ...ENGINE });
      http.expectOne('/api/settings/download-dir').flush(dir);
      flushRehydration(http);
      await openGear();
    };
    const choose = async () => {
      change().click();
      await settle();
      return http.expectOne('/api/settings/download-dir/choose');
    };

    it('shows the folder loaded at start, with the full path as title and no Restablecer', async () => {
      await load();

      expect(el('[data-testid=download-dir]')?.textContent).toContain('Carpeta de descargas');
      expect(dirEl('path')?.textContent?.trim()).toBe('~/Downloads');
      expect(dirEl('path')?.getAttribute('title')).toBe('/Users/ana/Downloads');
      expect(dirEl('path')?.className).toContain('truncate');
      expect(dirEl('path')?.className).not.toContain('text-accent');
      expect(change().textContent).toContain('Cambiar…');
      expect(dirEl('reset')).toBeNull();
      expect(dirEl('unavailable')).toBeNull();
    });

    it('is not shown until the server reports the folder', async () => {
      http.expectOne('/api/health').flush(HEALTH);
      await openGear();

      expect(el('[data-testid=download-dir]')).toBeNull();
    });

    it('chooses a folder: disables Cambiar… with a spinner while the dialog is open', async () => {
      await load();
      const req = await choose();
      expect(req.request.method).toBe('POST');
      expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
      expect(change().disabled).toBe(true);
      expect(dirEl('spinner')).not.toBeNull();

      req.flush(CUSTOM_DIR);
      await settle();

      expect(change().disabled).toBe(false);
      expect(dirEl('spinner')).toBeNull();
      expect(dirEl('path')?.textContent?.trim()).toBe('/Volumes/Disco/Música');
      expect(dirEl('reset')?.textContent).toContain('Restablecer');
      expect(dirEl('error')).toBeNull();
    });

    it('does nothing when the dialog is canceled', async () => {
      await load();
      (await choose()).flush({ canceled: true });
      await settle();

      expect(change().disabled).toBe(false);
      expect(dirEl('path')?.textContent?.trim()).toBe('~/Downloads');
      expect(dirEl('error')).toBeNull();
    });

    it.each([
      [
        501,
        'picker_unavailable',
        'Esta acción solo funciona en la aplicación de escritorio (macOS o Windows).',
      ],
      [409, 'picker_busy', 'Ya hay un diálogo abierto.'],
      [422, 'download_dir_not_writable', 'No se puede escribir en esa carpeta. Elige otra.'],
    ])('shows the server message when choose answers %i', async (status, code, message) => {
      await load();
      (await choose()).flush({ code, message }, { status, statusText: 'x' });
      await settle();

      expect(dirEl('error')?.textContent?.trim()).toBe(message);
      expect(dirEl('error')?.getAttribute('role')).toBe('alert');
      expect(change().disabled).toBe(false);
      expect(dirEl('path')?.textContent?.trim()).toBe('~/Downloads');
    });

    it('shows a generic message when the server cannot be reached, and clears it on retry', async () => {
      await load();
      (await choose()).error(new ProgressEvent('error'));
      await settle();
      expect(dirEl('error')?.textContent?.trim()).toBe('No se pudo cambiar la carpeta.');

      change().click();
      await settle();
      expect(dirEl('error')).toBeNull();
      http.expectOne('/api/settings/download-dir/choose').flush({ canceled: true });
    });

    it('Restablecer deletes the setting and goes back to the default', async () => {
      await load(CUSTOM_DIR);
      dirEl('reset')!.click();
      await settle();

      const req = http.expectOne('/api/settings/download-dir');
      expect(req.request.method).toBe('DELETE');
      expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
      req.flush(DIR);
      await settle();

      expect(dirEl('path')?.textContent?.trim()).toBe('~/Downloads');
      expect(dirEl('reset')).toBeNull();
    });

    it('follows settings.updated from another tab', async () => {
      await load();

      stream().emit('settings.updated', CUSTOM_DIR);
      await settle();
      expect(dirEl('path')?.textContent?.trim()).toBe('/Volumes/Disco/Música');
      expect(dirEl('reset')).not.toBeNull();

      stream().emit('settings.updated', DIR);
      await settle();
      expect(dirEl('path')?.textContent?.trim()).toBe('~/Downloads');
      expect(dirEl('reset')).toBeNull();
    });

    it('fetches the folder again when the stream reconnects', async () => {
      await load();

      stream().open();
      http.expectOne('/api/system/engine').flush({ ...ENGINE });
      http.expectOne('/api/settings/download-dir').flush(CUSTOM_DIR);
      flushRehydration(http);
      await settle();

      expect(dirEl('path')?.textContent?.trim()).toBe('/Volumes/Disco/Música');
    });

    it('marks an unavailable folder in the error colour with "No disponible"', async () => {
      await load({ ...CUSTOM_DIR, available: false });

      expect(dirEl('path')?.className).toContain('text-accent');
      expect(dirEl('unavailable')?.textContent?.trim()).toBe('No disponible');
      expect(dirEl('unavailable')?.className).toContain('text-accent');
      expect(dirEl('reset')).not.toBeNull();
    });
  });

  it('labels the reveal button from the platform that /api/health reports', async () => {
    http.expectOne('/api/health').flush({ ...HEALTH, platform: 'darwin' });
    await fixture.whenStable();

    expect(TestBed.inject(SystemService).platform()).toBe('darwin');
  });
});
