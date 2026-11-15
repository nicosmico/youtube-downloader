import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PRESET_480, PRESET_BEST, PRESET_MP3 } from '../../testing/fixtures';
import { appHeaderInterceptor } from '../core/api.interceptor';
import { Preset, PresetsService } from '../core/presets.service';
import { Presets } from './presets';

describe('Presets', () => {
  let fixture: ComponentFixture<Presets>;
  let http: HttpTestingController;
  let service: PresetsService;
  let applied: Preset[];

  const root = () => fixture.nativeElement as HTMLElement;
  const el = <T extends HTMLElement>(testId: string) =>
    root().querySelector(`[data-testid=${testId}]`) as T | null;
  const all = (testId: string) =>
    Array.from(root().querySelectorAll<HTMLElement>(`[data-testid=${testId}]`));
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const click = async (testId: string) => {
    el(testId)!.click();
    await settle();
  };
  const typeInto = async (testId: string, value: string) => {
    const input = el<HTMLInputElement>(testId)!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    await settle();
  };
  const chipNames = () => all('preset-apply').map((c) => c.textContent?.trim());
  const refuse = async (code: string, message: string, status: number) => {
    http
      .expectOne((r) => r.url.startsWith('/api/presets'))
      .flush({ code, message }, { status, statusText: 'x' });
    await settle();
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Presets],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    service = TestBed.inject(PresetsService);
    service.presets.set([PRESET_BEST, PRESET_MP3]);
    fixture = TestBed.createComponent(Presets);
    fixture.componentRef.setInput('mode', 'video');
    fixture.componentRef.setInput('quality', '720p');
    fixture.componentRef.setInput('audioFormat', 'm4a');
    applied = [];
    fixture.componentInstance.applied.subscribe((p) => applied.push(p));
    await settle();
  });

  afterEach(() => http.verify());

  it('lists the presets as buttons', () => {
    expect(chipNames()).toEqual(['Mejor video', 'MP3']);
  });

  it('says so when there are no presets', async () => {
    service.presets.set([]);
    await settle();

    expect(el('presets-empty')?.textContent).toContain('Todavía no tienes presets');
    expect(el('preset-manage')).toBeNull();
  });

  it('emits the preset on a single click', async () => {
    await click('preset-apply');

    expect(applied).toEqual([PRESET_BEST]);
  });

  describe('save as preset', () => {
    beforeEach(async () => {
      await click('preset-save-open');
    });

    it('sends the current video options with the trimmed name', async () => {
      await typeInto('preset-name-input', '  Ligero ');
      await click('preset-save');

      const req = http.expectOne('/api/presets');
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ name: 'Ligero', mode: 'video', quality: '720p' });
      req.flush({ ...PRESET_480, name: 'Ligero' });
      await settle();

      expect(chipNames()).toEqual(['Ligero', 'Mejor video', 'MP3']);
      expect(el('preset-save-form')).toBeNull();
    });

    it('sends the audio format in audio mode', async () => {
      fixture.componentRef.setInput('mode', 'audio');
      await settle();
      await typeInto('preset-name-input', 'Música');
      await click('preset-save');

      const req = http.expectOne('/api/presets');
      expect(req.request.body).toEqual({ name: 'Música', mode: 'audio', audioFormat: 'm4a' });
      req.flush({ ...PRESET_MP3, id: 'p9', name: 'Música', audioFormat: 'm4a' });
    });

    it('saves with Enter', async () => {
      await typeInto('preset-name-input', 'Rápido');
      el<HTMLFormElement>('preset-save-form')!.dispatchEvent(new Event('submit'));
      await settle();

      http.expectOne('/api/presets').flush({ ...PRESET_480, name: 'Rápido' });
    });

    it('rejects an empty name without a request', async () => {
      await typeInto('preset-name-input', '   ');
      await click('preset-save');

      expect(el('preset-error')?.textContent).toContain('Escribe un nombre');
    });

    it('shows the duplicate name error and stays open to fix it', async () => {
      await typeInto('preset-name-input', 'mp3');
      await click('preset-save');
      await refuse('preset_name_taken', 'Ya existe un preset llamado «mp3».', 409);

      expect(el('preset-error')?.textContent).toContain('Ya existe un preset con ese nombre');
      expect(el('preset-name-input')).not.toBeNull();
      expect(chipNames()).toEqual(['Mejor video', 'MP3']);
    });

    it('shows the invalid options error', async () => {
      await typeInto('preset-name-input', 'Mala');
      await click('preset-save');
      await refuse('invalid_options', 'x', 422);

      expect(el('preset-error')?.textContent).toContain('no se pueden guardar');
    });

    it('cancels and clears the error', async () => {
      await typeInto('preset-name-input', '');
      await click('preset-save');
      await click('preset-save-cancel');

      expect(el('preset-save-form')).toBeNull();
      expect(el('preset-error')).toBeNull();
    });
  });

  describe('manage', () => {
    const rowOf = (id: string) =>
      root().querySelector(`[data-testid=preset-row][data-preset-id=${id}]`) as HTMLElement;
    const within = (id: string, testId: string) =>
      rowOf(id).querySelector(`[data-testid=${testId}]`) as HTMLElement;

    beforeEach(async () => {
      await click('preset-manage');
    });

    it('shows each preset with its options', () => {
      expect(all('preset-row')).toHaveLength(2);
      expect(rowOf('p2').textContent).toContain('Audio · MP3');
      expect(rowOf('p1').textContent).toContain('Video · mejor disponible');
    });

    it('renames: sends the new name and updates the list', async () => {
      within('p2', 'preset-rename').click();
      await settle();
      const input = within('p2', 'preset-rename-input') as HTMLInputElement;
      expect(input.value).toBe('MP3');
      input.value = ' Solo audio ';
      within('p2', 'preset-rename-save').click();
      await settle();

      const req = http.expectOne('/api/presets/p2');
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body).toEqual({ name: 'Solo audio' });
      req.flush({ ...PRESET_MP3, name: 'Solo audio' });
      await settle();

      expect(chipNames()).toEqual(['Mejor video', 'Solo audio']);
      expect(el('preset-rename-input')).toBeNull();
    });

    it('shows the duplicate name error when renaming to an existing name', async () => {
      within('p2', 'preset-rename').click();
      await settle();
      (within('p2', 'preset-rename-input') as HTMLInputElement).value = 'MEJOR VIDEO';
      within('p2', 'preset-rename-save').click();
      await settle();
      await refuse('preset_name_taken', 'Ya existe', 409);

      expect(el('preset-error')?.textContent).toContain('Ya existe un preset con ese nombre');
      expect(chipNames()).toEqual(['Mejor video', 'MP3']);
    });

    it('asks before deleting and does nothing on cancel', async () => {
      within('p1', 'preset-delete').click();
      await settle();

      expect(el('preset-delete-question')?.textContent).toContain('«Mejor video»');
      await click('preset-edit-cancel');

      expect(chipNames()).toEqual(['Mejor video', 'MP3']);
      expect(within('p1', 'preset-delete')).not.toBeNull();
    });

    it('deletes after confirming', async () => {
      within('p1', 'preset-delete').click();
      await settle();
      await click('preset-delete-confirm');

      const req = http.expectOne('/api/presets/p1');
      expect(req.request.method).toBe('DELETE');
      req.flush(null, { status: 204, statusText: 'No Content' });
      await settle();

      expect(chipNames()).toEqual(['MP3']);
    });

    it('explains a delete of a preset that is already gone', async () => {
      within('p1', 'preset-delete').click();
      await settle();
      await click('preset-delete-confirm');
      await refuse('preset_not_found', 'x', 404);

      expect(el('preset-error')?.textContent).toContain('ya no existe');
    });
  });
});
