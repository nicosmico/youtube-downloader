import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { PRESET_480, PRESET_BEST, PRESET_MP3 } from '../../testing/fixtures';
import { appHeaderInterceptor } from './api.interceptor';
import { PresetError, PresetsService } from './presets.service';

describe('PresetsService', () => {
  let service: PresetsService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(PresetsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  const names = () => service.presets().map((p) => p.name);

  it('loads the list and keeps it sorted by name, ignoring case and accents', () => {
    service.load();
    http
      .expectOne('/api/presets')
      .flush([
        PRESET_MP3,
        { ...PRESET_BEST, id: 'a', name: 'zeta' },
        { ...PRESET_BEST, id: 'b', name: 'Álamo' },
        { ...PRESET_BEST, id: 'c', name: 'alfa' },
      ]);

    expect(names()).toEqual(['Álamo', 'alfa', 'MP3', 'zeta']);
  });

  it('keeps an empty list if loading fails', () => {
    service.load();
    http.expectOne('/api/presets').flush('', { status: 500, statusText: 'x' });

    expect(service.presets()).toEqual([]);
  });

  it('creates with the options of the mode and adds it in order', () => {
    service.presets.set([PRESET_BEST, PRESET_MP3]);

    service.create('Ligero', { mode: 'video', quality: '480p' }).subscribe();
    const req = http.expectOne('/api/presets');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ name: 'Ligero', mode: 'video', quality: '480p' });
    req.flush(PRESET_480);

    expect(names()).toEqual(['Ligero', 'Mejor video', 'MP3']);
  });

  it('renames with PATCH and replaces the item', () => {
    service.presets.set([PRESET_BEST, PRESET_MP3]);

    service.rename('p2', 'Audio').subscribe();
    const req = http.expectOne('/api/presets/p2');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ name: 'Audio' });
    req.flush({ ...PRESET_MP3, name: 'Audio' });

    expect(names()).toEqual(['Audio', 'Mejor video']);
  });

  it('deletes with DELETE and drops the item', () => {
    service.presets.set([PRESET_BEST, PRESET_MP3]);

    service.remove('p1').subscribe();
    const req = http.expectOne('/api/presets/p1');
    expect(req.request.method).toBe('DELETE');
    req.flush(null, { status: 204, statusText: 'No Content' });

    expect(names()).toEqual(['MP3']);
  });

  it('maps API refusals to a PresetError with the code and leaves the list alone', () => {
    service.presets.set([PRESET_BEST]);
    let error: PresetError | undefined;

    service.create('Mejor video', { mode: 'video', quality: 'best' }).subscribe({
      error: (e: PresetError) => (error = e),
    });
    http
      .expectOne('/api/presets')
      .flush(
        { code: 'preset_name_taken', message: 'Ya existe un preset llamado «Mejor video».' },
        { status: 409, statusText: 'Conflict' },
      );

    expect(error).toBeInstanceOf(PresetError);
    expect(error?.code).toBe('preset_name_taken');
    expect(error?.message).toContain('Ya existe');
    expect(names()).toEqual(['Mejor video']);
  });

  it('reports "network" when the server does not answer', () => {
    let error: PresetError | undefined;

    service.remove('p1').subscribe({ error: (e: PresetError) => (error = e) });
    http.expectOne('/api/presets/p1').error(new ProgressEvent('error'));

    expect(error?.code).toBe('network');
  });
});
