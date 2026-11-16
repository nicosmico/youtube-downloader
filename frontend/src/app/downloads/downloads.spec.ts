import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FakeEventSource } from '../../testing/fake-event-source';
import { appHeaderInterceptor } from '../core/api.interceptor';
import { NOW } from '../core/clock';
import { EVENT_SOURCE_FACTORY } from '../core/event-stream.service';
import { installDialogPolyfill } from '../../testing/dialog';
import { JOB, jobAt, localIso } from '../../testing/fixtures';
import { flushRehydration } from '../../testing/rehydration';
import { Job, JobsService } from '../core/jobs.service';
import { SystemService } from '../core/system.service';
import { Downloads, formatBytes, groupJobs } from './downloads';

describe('Downloads', () => {
  let fixture: ComponentFixture<Downloads>;
  let http: HttpTestingController;
  let jobs: JobsService;

  const root = () => fixture.nativeElement as HTMLElement;
  const all = (testId: string) =>
    Array.from(root().querySelectorAll<HTMLElement>(`[data-testid=${testId}]`));
  const el = (testId: string) => all(testId)[0] ?? null;
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  /** Shows the jobs. */
  const show = async (...list: Partial<Job>[]) => {
    jobs.jobs.set(list.map((j, i) => ({ ...JOB, id: `job${i}`, ...j })));
    await settle();
  };
  const openMenu = async (index = 0) => {
    root().querySelectorAll<HTMLElement>('[data-testid=job-menu]')[index].click();
    await settle();
  };

  beforeEach(async () => {
    FakeEventSource.reset();
    await TestBed.configureTestingModule({
      imports: [Downloads],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(Downloads);
    await settle();
  });

  afterEach(() => http.verify());

  it('has no tabs: one list with the filters above it, "Todas" first and pressed', async () => {
    expect(root().querySelector('[role=tablist]')).toBeNull();
    expect(all('filters')).toHaveLength(1);
    expect(all('filters')[0].getAttribute('role')).toBe('group');
    const chips = Array.from(el('filters')!.querySelectorAll('button'));
    expect(chips.map((c) => c.textContent?.trim())).toEqual([
      'Todas',
      'En curso · 0',
      'Completadas',
      'Con error',
      'Canceladas',
    ]);
    expect(chips.map((c) => c.getAttribute('aria-pressed'))).toEqual([
      'true',
      'false',
      'false',
      'false',
      'false',
    ]);
  });

  it('counts the jobs of the Queue on the "En curso" chip (active + queued)', async () => {
    jobs.queue.set({ active: 2, queued: 3 });
    await settle();

    expect(el('filter-active')?.textContent?.trim()).toBe('En curso · 5');
  });

  it('keeps the filters in one row that scrolls instead of wrapping', async () => {
    const group = el('filters')!;
    expect(group.className).toContain('overflow-x-auto');
    expect(group.className).not.toContain('flex-wrap');
    for (const chip of Array.from(group.querySelectorAll('button'))) {
      expect(chip.className).toContain('shrink-0');
      expect(chip.className).toContain('whitespace-nowrap');
    }
  });

  it('shows the thumbnail of the job, or a neutral placeholder without one', async () => {
    await show({ status: 'queued' }, { status: 'queued', thumbnail: null });

    expect(el('job-thumbnail')?.getAttribute('src')).toBe(JOB.thumbnail);
    expect(el('job-thumbnail')?.getAttribute('referrerpolicy')).toBe('no-referrer');
    expect(all('job-thumbnail')).toHaveLength(1);
    expect(all('job-thumbnail-placeholder')).toHaveLength(1);
  });

  it('shows no explanatory text: icon buttons carry a tooltip and a label', async () => {
    await show({ status: 'downloading' });

    const cancel = el('cancel-job')!;
    expect(cancel.getAttribute('title')).toBe('Cancelar');
    expect(cancel.getAttribute('aria-label')).toBe('Cancelar');
    expect(cancel.textContent?.trim()).toBe('');
  });

  it('shows a queued job with its title and no progress bar', async () => {
    await show({ status: 'queued' });

    expect(el('job-title')?.textContent).toContain('Me at the zoo');
    expect(el('job-status')?.textContent).toContain('En cola');
    expect(el('job-progress')).toBeNull();
    expect(el('downloads-empty')).toBeNull();
  });

  it.each([
    [{ mode: 'video', quality: 'best', audioFormat: null }, 'Video · Mejor disponible'],
    [{ mode: 'video', quality: '720p', audioFormat: null }, 'Video · 720p'],
    [{ mode: 'audio', quality: null, audioFormat: 'mp3' }, 'Audio · MP3'],
    [{ mode: 'audio', quality: null, audioFormat: 'm4a' }, 'Audio · M4A'],
    [{ mode: 'audio', quality: null, audioFormat: 'opus' }, 'Audio · Opus'],
  ] as const)('shows what was requested on the status line: %j', async (options, label) => {
    await show({ ...options, status: 'processing' });

    expect(el('job-status')?.textContent?.trim()).toBe(`${label} · Procesando`);
  });

  it('uses a generic title when the job has none', async () => {
    await show({ title: null });

    expect(el('job-title')?.textContent).toContain('Video de YouTube');
  });

  it('shows one status line with the options, percentage and time left, and a thin bar', async () => {
    await show({
      status: 'downloading',
      mode: 'audio',
      quality: null,
      audioFormat: 'mp3',
      progressPercent: 44.6,
      downloadedBytes: 5 * 1024 * 1024,
      totalBytes: 12 * 1024 * 1024,
      speed: 2.5 * 1024 * 1024,
      eta: 12,
    });

    expect(el('job-status')?.textContent?.trim()).toBe('Audio · MP3 · 45 % · quedan 0:12');
    const bar = el('job-progress')!;
    expect(bar.getAttribute('role')).toBe('progressbar');
    expect(bar.getAttribute('aria-valuenow')).toBe('45');
    expect(el('job-progress-fill')?.style.width).toBe('45%');
    expect(bar.getAttribute('title')).toBe('5,0 MB / 12,0 MB · 2,5 MB/s');
  });

  it('shows "Preparando…" without a bar while no byte has arrived', async () => {
    await show({ status: 'downloading', progressPercent: 0, downloadedBytes: null });

    expect(el('job-status')?.textContent?.trim()).toBe('Video · Mejor disponible · Preparando…');
    expect(el('job-progress')).toBeNull();
    expect(el('cancel-job')).not.toBeNull();
  });

  it('switches to the progress line with the first progress update, and back on retry', async () => {
    jobs.connect();
    const stream = FakeEventSource.instances[0];
    stream.emit('job.updated', { ...JOB, status: 'downloading' });
    await settle();
    expect(el('job-status')?.textContent).toContain('Preparando…');

    stream.emit('job.updated', {
      ...JOB,
      status: 'downloading',
      progressPercent: 3,
      downloadedBytes: 4096,
    });
    await settle();
    expect(el('job-status')?.textContent).toContain('3 %');
    expect(el('job-progress')?.getAttribute('aria-valuenow')).toBe('3');

    // retry: the backend clears the progress of the previous Attempt
    stream.emit('job.updated', { ...JOB, status: 'queued', attempt: 2 });
    stream.emit('job.updated', { ...JOB, status: 'downloading', attempt: 2 });
    await settle();
    expect(el('job-status')?.textContent).toContain('Preparando…');
    expect(el('job-progress')).toBeNull();
  });

  it('copes with unknown totals, speed and ETA', async () => {
    await show({ status: 'downloading', downloadedBytes: 2048, totalBytes: null });

    expect(el('job-progress')?.getAttribute('title')).toBe('2,0 KB');
    expect(el('job-status')?.textContent).not.toContain('quedan');
  });

  it('shows a full bar without ETA while processing', async () => {
    await show({
      status: 'processing',
      progressPercent: 99,
      downloadedBytes: 1024,
      totalBytes: 1024,
      speed: 1000,
      eta: 3,
    });

    expect(el('job-status')?.textContent).toContain('Procesando');
    expect(el('job-progress')?.getAttribute('aria-valuenow')).toBe('100');
    expect(el('job-status')?.textContent).not.toContain('quedan');
  });

  it('offers "Abrir carpeta" on a completed job and shows the result', async () => {
    await show({ status: 'completed', progressPercent: 100 });
    expect(el('job-status')?.textContent).toContain('Completada');
    expect(el('job-progress')).toBeNull();

    await openMenu();
    (el('open-folder') as HTMLButtonElement).click();
    const req = http.expectOne('/api/system/open-downloads');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ status: 'opened' });
    await settle();

    expect(el('folder-message')?.textContent).toContain('Carpeta abierta');
  });

  it('shows the server message when the folder cannot be opened', async () => {
    await show({ status: 'completed' });

    await openMenu();
    (el('open-folder') as HTMLButtonElement).click();
    http
      .expectOne('/api/system/open-downloads')
      .flush(
        { code: 'open_unavailable', message: 'Solo funciona en la aplicación de escritorio.' },
        { status: 501, statusText: 'x' },
      );
    await settle();

    expect(el('folder-message')?.textContent).toContain('aplicación de escritorio');
    expect(el('folder-message')?.getAttribute('role')).toBe('alert');
  });

  it('shows the error of a failed job, without a folder button', async () => {
    await show({ status: 'failed', error: 'El video no está disponible.' });

    expect(el('job-status')?.textContent?.trim()).toBe('Fallida');
    expect(el('job-status')?.className).toContain('text-accent');
    expect(el('job-error')?.textContent).toContain('El video no está disponible.');
    await openMenu();
    expect(el('open-folder')).toBeNull();
  });

  it('labels an interrupted job in Spanish with the reason and no progress or folder button', async () => {
    await show({
      status: 'interrupted',
      error: 'La aplicación se cerró durante la descarga.',
      progressPercent: 40,
    });

    expect(el('job-status')?.textContent).toContain('Interrumpida');
    expect(el('job-card')?.getAttribute('data-status')).toBe('interrupted');
    expect(el('job-error')?.textContent).toContain('La aplicación se cerró durante la descarga.');
    expect(el('job-progress')).toBeNull();
    expect(el('open-folder')).toBeNull();
    expect(el('retry-job')).not.toBeNull();
  });

  it('follows the jobs without a reload: the count and each status line', async () => {
    jobs.connect();
    const stream = FakeEventSource.instances[0];
    expect(el('filter-active')?.textContent?.trim()).toBe('En curso · 0');

    for (const [id, n] of [
      ['a', 1],
      ['b', 2],
      ['c', 3],
    ] as const) {
      stream.emit('job.updated', { ...JOB, id, createdAt: `2026-11-15T12:00:0${n}.000000+00:00` });
    }
    stream.emit('queue.updated', { active: 0, queued: 3 });
    await settle();
    expect(el('filter-active')?.textContent?.trim()).toBe('En curso · 3');
    expect(all('job-status').map((s) => s.textContent?.trim())).toEqual([
      'En cola',
      'En cola',
      'En cola',
    ]);

    // two slots are taken: the oldest two start, the newest keeps waiting
    for (const [id, n] of [
      ['a', 1],
      ['b', 2],
    ] as const) {
      stream.emit('job.updated', {
        ...JOB,
        id,
        createdAt: `2026-11-15T12:00:0${n}.000000+00:00`,
        status: 'downloading',
        downloadedBytes: 1024,
      });
    }
    await settle();
    expect(all('job-status').map((s) => s.textContent?.trim())).toEqual([
      'En cola',
      'Video · Mejor disponible · 0 %',
      'Video · Mejor disponible · 0 %',
    ]);
  });

  it('renders one card per job, newest first, and follows SSE updates', async () => {
    jobs.connect();
    const stream = FakeEventSource.instances[0];
    stream.emit('job.updated', JOB);
    stream.emit('job.updated', {
      ...JOB,
      id: 'job2',
      title: 'Otro',
      createdAt: '2026-11-15T12:01:00.000000+00:00',
    });
    await settle();
    expect(all('job-title').map((t) => t.textContent?.trim())).toEqual(['Otro', 'Me at the zoo']);

    stream.emit('job.updated', {
      ...JOB,
      status: 'downloading',
      progressPercent: 10,
      downloadedBytes: 1024,
    });
    await settle();

    expect(all('job-card')).toHaveLength(2);
    expect(all('job-status')[1].textContent).toContain('10 %');
    expect(all('job-card')[1].getAttribute('data-status')).toBe('downloading');
  });

  it('rehydrates on reconnect', async () => {
    jobs.connect();
    FakeEventSource.instances[0].open();
    flushRehydration(http, { history: [{ ...JOB, status: 'failed', error: 'Falló.' }] });
    await settle();

    expect(el('job-error')?.textContent).toContain('Falló.');
  });
});

describe('batches', () => {
  const batchJob = (n: number, extra: Partial<Job> = {}): Partial<Job> => ({
    batchId: 'b1',
    batchTitle: 'Mi playlist',
    batchEntryCount: 3,
    playlistIndex: n,
    title: `Video ${n}`,
    createdAt: `2026-11-15T12:00:0${n}.000000+00:00`,
    ...extra,
  });
  let fixture: ComponentFixture<Downloads>;
  let jobs: JobsService;
  const root = () => fixture.nativeElement as HTMLElement;
  const all = (testId: string) =>
    Array.from(root().querySelectorAll<HTMLElement>(`[data-testid=${testId}]`));
  const show = async (...list: Partial<Job>[]) => {
    jobs.jobs.set(list.map((j, i) => ({ ...JOB, id: `job${i}`, ...j })));
    await fixture.whenStable();
    fixture.detectChanges();
  };

  beforeEach(async () => {
    FakeEventSource.reset();
    await TestBed.configureTestingModule({
      imports: [Downloads],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    }).compileComponents();
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(Downloads);
    await fixture.whenStable();
  });

  it('groups the jobs of a batch under its title, in playlist order, with an aggregate', async () => {
    await show(
      batchJob(3, { id: 'c', status: 'queued' }),
      batchJob(1, { id: 'a', status: 'processing' }),
      batchJob(2, { id: 'b', status: 'downloading', progressPercent: 40 }),
    );

    expect(all('batch')).toHaveLength(1);
    expect(all('batch-title')[0].textContent).toContain('Mi playlist');
    expect(all('batch-summary')[0].textContent).toContain('0/3 completadas');
    expect(all('batch-summary')[0].textContent).toContain('2 en curso');
    expect(all('job-status').map((s) => s.textContent?.trim())).toEqual([
      'Video · Mejor disponible · Procesando',
      'Video · Mejor disponible · Preparando…',
      'En cola',
    ]);
    const cards = all('job-card');
    expect(cards).toHaveLength(3);
    expect(all('job-title').map((t) => t.textContent?.trim())).toEqual([
      'Video 1',
      'Video 2',
      'Video 3',
    ]);
    expect(root().querySelectorAll('[data-testid=batch] [data-testid=job-card]')).toHaveLength(3);
  });

  it('keeps the jobs individual: each has its own status and error', async () => {
    await show(
      batchJob(1, { status: 'completed' }),
      batchJob(2, { status: 'failed', error: 'El video es privado' }),
      batchJob(3, { status: 'completed' }),
    );

    expect(all('job-status').map((s) => s.textContent?.trim())).toEqual([
      'Video · Mejor disponible · Completada',
      'Fallida',
      'Video · Mejor disponible · Completada',
    ]);
    expect(all('job-error')).toHaveLength(1);
    expect(all('batch-summary')[0].textContent).toContain('2/3 completadas');
    expect(all('batch-summary')[0].textContent).toContain('1 con error');
  });

  it('shows single videos next to a batch, each at the place of its newest job', async () => {
    await show(
      { id: 'solo', title: 'Suelto', createdAt: '2026-11-15T12:00:09.000000+00:00' },
      batchJob(2, { id: 'b2' }),
      batchJob(1, { id: 'b1' }),
    );

    expect(all('batch')).toHaveLength(1);
    expect(root().querySelector('[data-testid=batch] [data-testid=job-card]')).not.toBeNull();
    expect(all('job-title').map((t) => t.textContent?.trim())).toEqual([
      'Suelto',
      'Video 1',
      'Video 2',
    ]);
    expect(root().querySelectorAll('[data-testid=batch]')[0].textContent).not.toContain('Suelto');
  });

  it('keeps separate batches apart', async () => {
    await show(
      batchJob(1, { id: 'x1' }),
      batchJob(1, { id: 'y1', batchId: 'b2', batchTitle: 'Otra' }),
    );

    expect(all('batch-title').map((t) => t.textContent?.trim())).toEqual(['Mi playlist', 'Otra']);
  });

  it('groupJobs counts against the entries chosen, not only the jobs it knows', () => {
    const items = groupJobs([
      { ...JOB, ...batchJob(1, { status: 'completed' }), batchEntryCount: 10 } as Job,
    ]);

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ kind: 'batch', total: 10, completed: 1 });
  });
});

describe('Downloads cancel and retry', () => {
  let fixture: ComponentFixture<Downloads>;
  let http: HttpTestingController;
  let jobs: JobsService;

  const root = () => fixture.nativeElement as HTMLElement;
  const el = (testId: string) => root().querySelector<HTMLElement>(`[data-testid=${testId}]`);
  const click = async (testId: string) => {
    (el(testId) as HTMLButtonElement).click();
    await settle();
  };
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  /** Shows the jobs. */
  const show = async (...list: Partial<Job>[]) => {
    jobs.jobs.set(list.map((j, i) => ({ ...JOB, id: `job${i}`, ...j })));
    await settle();
  };
  const openMenu = async (index = 0) => {
    root().querySelectorAll<HTMLElement>('[data-testid=job-menu]')[index].click();
    await settle();
  };

  beforeEach(async () => {
    FakeEventSource.reset();
    await TestBed.configureTestingModule({
      imports: [Downloads],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(Downloads);
    await settle();
  });

  afterEach(() => http.verify());

  it.each([
    ['queued', true, false],
    ['downloading', true, false],
    ['processing', true, false],
    ['completed', false, false],
    ['failed', false, true],
    ['canceled', false, true],
    ['interrupted', false, true],
  ] as const)('%s: cancel=%s retry=%s', async (status, cancel, retry) => {
    await show({ status });

    expect(el('cancel-job') !== null).toBe(cancel);
    expect(el('retry-job') !== null).toBe(retry);
  });

  it('labels a canceled job "Cancelada"', async () => {
    await show({ status: 'canceled' });

    expect(el('job-status')?.textContent).toContain('Cancelada');
  });

  it('shows the attempt only from the second one', async () => {
    await show({ status: 'queued', attempt: 1 });
    expect(el('job-status')?.textContent?.trim()).toBe('En cola');

    await show({ status: 'queued', attempt: 2 });
    expect(el('job-status')?.textContent?.trim()).toBe('En cola · Intento 2');
  });

  it('cancels a queued job at once, without asking', async () => {
    await show({ status: 'queued' });

    await click('cancel-job');

    expect(el('cancel-confirm-text')).toBeNull();
    const req = http.expectOne('/api/jobs/job0/cancel');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ ...JOB, id: 'job0', status: 'canceled' });
    await settle();
    expect(el('downloads-empty')).toBeNull(); // it stays in the list
    expect(el('job-status')?.textContent).toContain('Cancelada');
    expect(el('retry-job')).not.toBeNull();
    expect(el('cancel-job')).toBeNull();
  });

  it('asks before cancelling a running job', async () => {
    await show({ status: 'downloading' });

    await click('cancel-job');
    expect(el('cancel-confirm-text')?.textContent).toContain('¿Cancelar esta descarga?');
    http.expectNone('/api/jobs/job0/cancel');

    await click('cancel-confirm-yes');
    const req = http.expectOne('/api/jobs/job0/cancel');
    expect(el('cancel-confirm-text')).toBeNull();
    expect((el('cancel-job') as HTMLButtonElement).disabled).toBe(true);
    req.flush({ ...JOB, id: 'job0', status: 'canceled' });
    await settle();
    expect(el('job-status')?.textContent).toContain('Cancelada');
  });

  it('keeps downloading when the confirmation is declined', async () => {
    await show({ status: 'processing' });

    await click('cancel-job');
    await click('cancel-confirm-no');

    http.expectNone('/api/jobs/job0/cancel');
    expect(el('cancel-confirm-text')).toBeNull();
    expect(el('cancel-job')).not.toBeNull();
  });

  it.each(['failed', 'canceled', 'interrupted'] as const)('retries a %s job', async (status) => {
    await show({ status, error: 'boom' });

    await click('retry-job');

    const req = http.expectOne('/api/jobs/job0/retry');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ ...JOB, id: 'job0', status: 'queued', attempt: 2 });
    await settle();
    expect(el('job-status')?.textContent?.trim()).toBe('En cola · Intento 2');
    expect(el('job-error')).toBeNull();
    expect(el('retry-job')).toBeNull();
  });

  it('tells the user when the job could not be cancelled and shows its real state', async () => {
    await show({ status: 'downloading' });

    await click('cancel-job');
    await click('cancel-confirm-yes');
    http
      .expectOne('/api/jobs/job0/cancel')
      .flush({ code: 'job_not_cancelable', message: 'x' }, { status: 409, statusText: 'x' });
    flushRehydration(http, { history: [{ ...JOB, id: 'job0', status: 'completed' }] });
    await settle();

    expect(el('action-message')?.textContent).toContain('No se pudo completar la acción');
    expect(el('job-status')?.textContent).toContain('Completada');
    expect(el('cancel-job')).toBeNull();
  });
});

describe('Downloads history', () => {
  let fixture: ComponentFixture<Downloads>;
  let http: HttpTestingController;
  let jobs: JobsService;
  let system: SystemService;

  const root = () => fixture.nativeElement as HTMLElement;
  const all = (testId: string) =>
    Array.from(root().querySelectorAll<HTMLElement>(`[data-testid=${testId}]`));
  const el = (testId: string) => all(testId)[0] ?? null;
  const within = (section: string, testId: string) =>
    Array.from(el(section)?.querySelectorAll<HTMLElement>(`[data-testid=${testId}]`) ?? []);
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const click = async (testId: string, index = 0) => {
    all(testId)[index].click();
    await settle();
  };
  /** Shows the jobs. */
  const show = async (...list: Partial<Job>[]) => {
    jobs.jobs.set(list.map((j, i) => ({ ...JOB, id: `job${i}`, ...j })));
    await settle();
  };
  const openMenu = async (index = 0) => {
    root().querySelectorAll<HTMLElement>('[data-testid=job-menu]')[index].click();
    await settle();
  };

  beforeEach(async () => {
    FakeEventSource.reset();
    await TestBed.configureTestingModule({
      imports: [Downloads],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    system = TestBed.inject(SystemService);
    fixture = TestBed.createComponent(Downloads);
    await settle();
  });

  afterEach(() => http.verify());

  it('shows every status in one list, newest first, wherever it is in the lifecycle', async () => {
    const at = (n: number) => `2026-11-15T12:00:0${n}.000000+00:00`;
    await show(
      { status: 'downloading', title: 'A', createdAt: at(7) },
      { status: 'queued', title: 'B', createdAt: at(6) },
      { status: 'processing', title: 'C', createdAt: at(5) },
      { status: 'completed', title: 'D', createdAt: at(4) },
      { status: 'failed', title: 'E', createdAt: at(3) },
      { status: 'canceled', title: 'F', createdAt: at(2) },
      { status: 'interrupted', title: 'G', createdAt: at(1) },
    );

    expect(all('job-title').map((t) => t.textContent?.trim())).toEqual([
      'A',
      'B',
      'C',
      'D',
      'E',
      'F',
      'G',
    ]);
  });

  it('brings back "Todas" when a new job joins the Queue under a filter that hides it', async () => {
    const old = { ...JOB, id: 'old', title: 'Viejo', status: 'completed' as const };
    jobs.connect();
    FakeEventSource.instances[0].open();
    flushRehydration(http, { history: [old] });
    await click('filter-completed');
    http
      .expectOne((r) => r.params.get('status') === 'completed')
      .flush({ jobs: [old], nextBefore: null });
    await settle();
    expect(el('filter-completed')?.getAttribute('aria-pressed')).toBe('true');

    jobs.jobs.update((list) => [
      { ...JOB, id: 'new', title: 'Nuevo', createdAt: '2026-11-15T13:00:00.000000+00:00' },
      ...list,
    ]);
    await settle();

    expect(el('filter-all')?.getAttribute('aria-pressed')).toBe('true');
    expect(all('job-title').map((t) => t.textContent?.trim())).toEqual(['Nuevo', 'Viejo']);
  });

  it('stays on "En curso" when the new job is shown there', async () => {
    await show({ status: 'completed', title: 'Viejo' });
    jobs.select('active');
    await settle();

    jobs.jobs.update((list) => [
      { ...JOB, id: 'new', title: 'Nuevo', createdAt: '2026-11-15T13:00:00.000000+00:00' },
      ...list,
    ]);
    await settle();

    expect(el('filter-active')?.getAttribute('aria-pressed')).toBe('true');
    expect(all('job-title').map((t) => t.textContent?.trim())).toEqual(['Nuevo']);
  });

  it('a job keeps its place when it finishes, and when it is retried', async () => {
    const at = (n: number) => `2026-11-15T12:00:0${n}.000000+00:00`;
    await show(
      { status: 'queued', title: 'Nuevo', createdAt: at(3) },
      { status: 'downloading', title: 'Medio', createdAt: at(2) },
      { status: 'completed', title: 'Viejo', createdAt: at(1) },
    );
    const titles = () => all('job-title').map((t) => t.textContent?.trim());
    expect(titles()).toEqual(['Nuevo', 'Medio', 'Viejo']);

    jobs.jobs.update((list) =>
      list.map((j) => (j.id === 'job1' ? { ...j, status: 'failed', error: 'x' } : j)),
    );
    await settle();
    expect(titles()).toEqual(['Nuevo', 'Medio', 'Viejo']);
    expect(all('job-card')[1].getAttribute('data-status')).toBe('failed');

    await click('retry-job');
    http.expectOne('/api/jobs/job1/retry').flush({
      ...JOB,
      id: 'job1',
      title: 'Medio',
      createdAt: at(2),
      status: 'queued',
      attempt: 2,
    });
    await settle();

    expect(titles()).toEqual(['Nuevo', 'Medio', 'Viejo']);
    expect(all('job-card')[1].getAttribute('data-status')).toBe('queued');
  });

  it('keeps the Batch grouping whatever the status of its jobs', async () => {
    const entry = (n: number, status: Job['status']): Partial<Job> => ({
      batchId: 'b1',
      batchTitle: 'Mi playlist',
      batchEntryCount: 3,
      playlistIndex: n,
      title: `Video ${n}`,
      status,
    });
    await show(entry(1, 'completed'), entry(2, 'completed'), entry(3, 'downloading'));

    expect(all('batch')).toHaveLength(1);
    expect(all('batch-summary')[0].textContent).toContain('2/3 completadas · 1 en curso');
    expect(all('job-title').map((t) => t.textContent?.trim())).toEqual([
      'Video 1',
      'Video 2',
      'Video 3',
    ]);

    // a filter shows only its jobs of the Batch, and the summary still counts them all
    jobs.select('active');
    await settle();
    expect(all('batch')).toHaveLength(1);
    expect(all('job-title').map((t) => t.textContent?.trim())).toEqual(['Video 3']);
    expect(all('batch-summary')[0].textContent).toContain('2/3 completadas · 1 en curso');
  });

  it('keeps "Quitar del historial" in the "⋮" menu, with a tooltip saying the file stays', async () => {
    await show({ status: 'completed' });

    expect(el('remove-job')).toBeNull();
    await openMenu();

    expect(el('remove-job')?.textContent).toContain('Quitar del historial');
    expect(el('remove-job')?.getAttribute('title')).toContain('el archivo descargado no se borra');
    expect(root().textContent).not.toContain('no borra el archivo');
  });

  it('opens the menu with the keyboard and closes it with Esc, back on the button', async () => {
    document.body.appendChild(root());
    await show({ status: 'completed' });

    await openMenu();
    expect(el('job-menu')?.getAttribute('aria-expanded')).toBe('true');
    expect(document.activeElement).toBe(el('open-folder'));

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await settle();

    expect(el('remove-job')).toBeNull();
    expect(document.activeElement).toBe(el('job-menu'));
    root().remove();
  });

  it.each(['completed', 'failed', 'canceled', 'interrupted'] as const)(
    'offers "Quitar del historial" for a %s job, which sends DELETE without asking',
    async (status) => {
      await show({ status, title: 'A' }, { status: 'completed', title: 'B' });

      await openMenu(0);
      await click('remove-job', 0);

      const req = http.expectOne('/api/jobs/job0');
      expect(req.request.method).toBe('DELETE');
      expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
      req.flush({ status: 'removed' });
      await settle();
      expect(all('job-title').map((t) => t.textContent?.trim())).toEqual(['B']);
    },
  );

  it('does not offer to remove queued or running jobs', async () => {
    await show({ status: 'queued' }, { status: 'downloading' }, { status: 'processing' });

    expect(el('job-menu')).toBeNull();
    expect(el('remove-job')).toBeNull();
  });

  it('shows an error and the real state when a removal fails', async () => {
    await show({ status: 'completed' });

    await openMenu();
    await click('remove-job');
    http
      .expectOne('/api/jobs/job0')
      .flush({ code: 'job_not_removable', message: 'x' }, { status: 409, statusText: 'x' });
    flushRehydration(http, { queue: [{ ...JOB, id: 'job0', status: 'queued' }] });
    await settle();

    expect(el('action-message')?.textContent).toContain('No se pudo completar la acción');
    expect(el('remove-job')).toBeNull();
    expect(el('job-status')?.textContent?.trim()).toBe('En cola');
  });

  it('removes a job another tab removed (job.removed)', async () => {
    jobs.connect();
    await show({ status: 'completed' });
    expect(el('job-card')).not.toBeNull();

    FakeEventSource.instances[0].emit('job.removed', { id: 'job0' });
    await settle();

    expect(el('job-card')).toBeNull();
    expect(el('downloads-empty')).not.toBeNull();
  });

  describe('reveal', () => {
    it('only completed jobs have the button, labelled for the platform', async () => {
      await show({ status: 'completed' }, { status: 'failed' }, { status: 'queued' });
      expect(all('reveal-job')).toHaveLength(1);
      expect(el('reveal-job')?.getAttribute('aria-label')).toBe('Mostrar archivo');
      expect(el('reveal-job')?.getAttribute('title')).toBe('Mostrar archivo');

      system.platform.set('darwin');
      await settle();
      expect(el('reveal-job')?.getAttribute('aria-label')).toBe('Mostrar en Finder');

      system.platform.set('win32');
      await settle();
      expect(el('reveal-job')?.getAttribute('title')).toBe('Mostrar en el Explorador');
    });

    it('asks the server and is disabled while it works', async () => {
      await show({ status: 'completed' });

      await click('reveal-job');
      const req = http.expectOne('/api/jobs/job0/reveal');
      expect(req.request.method).toBe('POST');
      expect((el('reveal-job') as HTMLButtonElement).disabled).toBe(true);
      req.flush({ status: 'revealed' });
      await settle();

      expect((el('reveal-job') as HTMLButtonElement).disabled).toBe(false);
      expect(el('reveal-error')).toBeNull();
    });

    it.each([
      [404, 'file_missing', 'El archivo ya no está en su carpeta: se movió o se eliminó.'],
      [501, 'open_unavailable', 'Esta acción solo funciona en la aplicación de escritorio.'],
    ])('shows the server message on %d', async (status, code, message) => {
      await show({ status: 'completed', title: 'A' }, { status: 'completed', title: 'B' });

      await click('reveal-job', 0);
      http.expectOne('/api/jobs/job0/reveal').flush({ code, message }, { status, statusText: 'x' });
      await settle();

      expect(all('reveal-error')).toHaveLength(1);
      expect(el('reveal-error')?.textContent).toContain(message);
      expect(el('reveal-error')?.getAttribute('role')).toBe('alert');
      expect((el('reveal-job') as HTMLButtonElement).disabled).toBe(false);
    });

    it('falls back to a generic message when the server cannot be reached', async () => {
      await show({ status: 'completed' });

      await click('reveal-job');
      http.expectOne('/api/jobs/job0/reveal').error(new ProgressEvent('error'));
      await settle();

      expect(el('reveal-error')?.textContent).toContain('No se pudo mostrar el archivo.');
    });
  });

  describe('load more', () => {
    const history = (id: string, createdAt: string): Job => ({
      ...JOB,
      id,
      status: 'completed',
      title: id,
      createdAt,
    });

    it('is offered only while the server has an older page', async () => {
      jobs.connect();
      FakeEventSource.instances[0].open();
      flushRehydration(http, {
        history: [history('h2', '2026-11-15T12:00:02.000000+00:00')],
        nextBefore: 'h2',
      });
      await settle();
      expect(el('load-more')?.textContent).toContain('Cargar más');

      await click('load-more');
      const req = http.expectOne((r) => r.url === '/api/jobs');
      expect(req.request.params.get('before')).toBe('h2');
      expect((el('load-more') as HTMLButtonElement).disabled).toBe(true);
      req.flush({
        jobs: [history('h1', '2026-11-15T12:00:01.000000+00:00')],
        nextBefore: null,
      });
      await settle();

      expect(all('job-title').map((t) => t.textContent?.trim())).toEqual(['h2', 'h1']);
      expect(el('load-more')).toBeNull();
    });
  });
});

describe('Downloads "Ver detalle"', () => {
  let fixture: ComponentFixture<Downloads>;
  let http: HttpTestingController;
  let jobs: JobsService;

  const root = () => fixture.nativeElement as HTMLElement;
  const el = (testId: string) => root().querySelector<HTMLElement>(`[data-testid=${testId}]`);
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const click = async (testId: string) => {
    el(testId)!.click();
    await settle();
  };
  /** Shows the jobs. */
  const show = async (...list: Partial<Job>[]) => {
    jobs.jobs.set(list.map((j, i) => ({ ...JOB, id: `job${i}`, ...j })));
    await settle();
  };
  const openMenu = async (index = 0) => {
    root().querySelectorAll<HTMLElement>('[data-testid=job-menu]')[index].click();
    await settle();
  };
  const FAILED = { status: 'failed', error: 'No se pudo descargar.' } as const;

  beforeEach(async () => {
    FakeEventSource.reset();
    await TestBed.configureTestingModule({
      imports: [Downloads],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(Downloads);
    await settle();
  });

  afterEach(() => http.verify());

  it.each(['queued', 'downloading', 'completed', 'canceled', 'interrupted'] as const)(
    'is not offered for a %s job',
    async (status) => {
      await show({ status });
      if (el('job-menu')) {
        await openMenu();
      }

      expect(el('job-detail-toggle')).toBeNull();
    },
  );

  it('asks nothing until "Ver detalle" is pressed, then shows the output', async () => {
    await show(FAILED);
    await openMenu();
    expect(el('job-detail-toggle')?.textContent).toContain('Ver detalle');
    http.expectNone('/api/jobs/job0/output');

    await click('job-detail-toggle');
    expect(el('job-detail-loading')).not.toBeNull();
    http
      .expectOne('/api/jobs/job0/output')
      .flush({ attempt: 1, lines: ['WARNING: algo', 'ERROR: Video unavailable'] });
    await settle();

    expect(el('job-detail')?.textContent).toBe('WARNING: algo\nERROR: Video unavailable');
    await openMenu();
    expect(el('job-detail-toggle')?.textContent).toContain('Ocultar detalle');
    expect(el('job-detail-toggle')?.getAttribute('aria-expanded')).toBe('true');
  });

  it('hides the output again', async () => {
    await show(FAILED);
    await openMenu();
    await click('job-detail-toggle');
    http.expectOne('/api/jobs/job0/output').flush({ attempt: 1, lines: ['x'] });
    await settle();

    await openMenu();
    await click('job-detail-toggle');

    expect(el('job-detail')).toBeNull();
    await openMenu();
    expect(el('job-detail-toggle')?.textContent).toContain('Ver detalle');
  });

  it('says so when there is no stored detail', async () => {
    await show(FAILED);
    await openMenu();
    await click('job-detail-toggle');

    http
      .expectOne('/api/jobs/job0/output')
      .flush(
        { code: 'output_unavailable', message: 'No hay detalle guardado de esta descarga.' },
        { status: 404, statusText: 'Not Found' },
      );
    await settle();

    expect(el('job-detail-error')?.textContent).toContain('No hay detalle guardado');
  });

  it('says so when the detail cannot be loaded', async () => {
    await show(FAILED);
    await openMenu();
    await click('job-detail-toggle');

    http.expectOne('/api/jobs/job0/output').flush({}, { status: 500, statusText: 'Error' });
    await settle();

    expect(el('job-detail-error')?.textContent).toContain('No se pudo cargar el detalle');
  });

  it('closes the detail on retry and does not show the old one after a new failure', async () => {
    await show(FAILED);
    await openMenu();
    await click('job-detail-toggle');
    http.expectOne('/api/jobs/job0/output').flush({ attempt: 1, lines: ['old output'] });
    await settle();

    await click('retry-job');
    http
      .expectOne('/api/jobs/job0/retry')
      .flush({ ...JOB, id: 'job0', status: 'queued', attempt: 2 });
    await settle();
    expect(el('job-detail')).toBeNull();

    jobs.jobs.set([{ ...JOB, id: 'job0', ...FAILED, attempt: 2 }]);
    await settle();

    expect(el('job-detail')).toBeNull();
    await openMenu();
    expect(el('job-detail-toggle')?.textContent).toContain('Ver detalle');
  });

  it('forgets the detail when the job leaves the History', async () => {
    await show(FAILED);
    await openMenu();
    await click('job-detail-toggle');
    http.expectOne('/api/jobs/job0/output').flush({ attempt: 1, lines: ['old output'] });
    await settle();

    await openMenu();
    await click('remove-job');
    http.expectOne('/api/jobs/job0').flush({ status: 'removed' });
    await settle();
    await show({ ...JOB, ...FAILED });

    expect(el('job-detail')).toBeNull();
  });
});

describe('Downloads filters, days and cleaning', () => {
  let fixture: ComponentFixture<Downloads>;
  let http: HttpTestingController;
  let jobs: JobsService;

  const root = () => fixture.nativeElement as HTMLElement;
  const all = (testId: string) =>
    Array.from(root().querySelectorAll<HTMLElement>(`[data-testid=${testId}]`));
  const el = (testId: string) => all(testId)[0] ?? null;
  const settle = async () => {
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const click = async (testId: string, index = 0) => {
    all(testId)[index].click();
    await settle();
  };
  const titles = () => all('job-title').map((t) => t.textContent?.trim());
  const headers = () => all('day-header').map((h) => h.textContent?.trim());
  const status = (r: { params: { get(name: string): string | null } }) => r.params.get('status');
  const page = (list: Job[], nextBefore: string | null = null) => ({ jobs: list, nextBefore });
  /** Answers the request of a filter's page. */
  const answer = (statuses: string, body: ReturnType<typeof page>) =>
    http.expectOne((r) => r.url === '/api/jobs' && status(r) === statuses).flush(body);
  /** The browser's local time of 16 November 2026, 15:00. */
  const NOW_AT = () => new Date(2026, 10, 16, 15, 0);
  const at = (day: number, hour = 12, month = 11, year = 2026) => localIso(year, month, day, hour);

  beforeEach(async () => {
    installDialogPolyfill();
    FakeEventSource.reset();
    await TestBed.configureTestingModule({
      imports: [Downloads],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
        { provide: NOW, useValue: NOW_AT },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    jobs = TestBed.inject(JobsService);
    fixture = TestBed.createComponent(Downloads);
    await settle();
  });

  afterEach(() => {
    root().remove();
    http.verify();
  });

  describe('filters', () => {
    const list: Job[] = [
      jobAt('q', at(16, 14), { status: 'queued' }),
      jobAt('d', at(16, 13), { status: 'downloading' }),
      jobAt('c', at(16, 12), { status: 'completed' }),
      jobAt('f', at(16, 11), { status: 'failed' }),
      jobAt('i', at(16, 10), { status: 'interrupted' }),
      jobAt('x', at(16, 9), { status: 'canceled' }),
    ];

    it('uses toggle buttons, with only the current filter pressed', async () => {
      jobs.jobs.set(list);
      await settle();

      await click('filter-completed');
      answer('completed', page([list[2]]));
      await settle();

      const pressed = all('filters')[0].querySelectorAll('[aria-pressed=true]');
      expect(pressed).toHaveLength(1);
      expect(pressed[0].textContent?.trim()).toBe('Completadas');
    });

    it.each([
      ['all', ['q', 'd', 'c', 'f', 'i', 'x']],
      ['active', ['q', 'd']],
      ['completed', ['c']],
      ['failed', ['f', 'i']],
      ['canceled', ['x']],
    ] as const)('"%s" shows %j', async (filter, expected) => {
      jobs.jobs.set(list);
      await settle();
      if (filter !== 'all') {
        await click(`filter-${filter}`);
        if (filter !== 'active') {
          http.match((r) => r.url === '/api/jobs'); // its page: the list is already known
        }
      }

      expect(titles()).toEqual(expected);
    });

    it.each([
      ['completed', 'completed'],
      ['failed', 'failed,interrupted'],
      ['canceled', 'canceled'],
    ] as const)('"%s" asks for its own jobs (status=%s) and shows them', async (filter, query) => {
      await click(`filter-${filter}`);

      const req = http.expectOne((r) => r.url === '/api/jobs');
      expect(status(req.request)).toBe(query);
      expect(req.request.params.get('limit')).toBe('50');
      req.flush(
        page([
          jobAt('on-server', at(1), {
            status:
              filter === 'completed' ? 'completed' : filter === 'failed' ? 'failed' : 'canceled',
          }),
        ]),
      );
      await settle();

      expect(titles()).toEqual(['on-server']);
    });

    it('does not say "no hay descargas" while the first page of a filter is on its way', async () => {
      await click('filter-completed');
      expect(el('downloads-empty')).toBeNull();

      answer('completed', page([]));
      await settle();

      expect(el('downloads-empty')?.textContent?.trim()).toBe('No hay descargas completadas.');
    });

    it.each([
      ['all', 'No hay descargas.'],
      ['active', 'No hay descargas en curso.'],
      ['completed', 'No hay descargas completadas.'],
      ['failed', 'No hay descargas con error.'],
      ['canceled', 'No hay descargas canceladas.'],
    ] as const)(
      'says "%s" is empty with a short sentence and no help',
      async (filter, sentence) => {
        if (filter !== 'all') {
          await click(`filter-${filter}`);
          if (filter !== 'active') {
            http.match((r) => r.url === '/api/jobs').forEach((r) => r.flush(page([])));
            await settle();
          }
        }

        expect(el('downloads-empty')?.textContent?.trim()).toBe(sentence);
        expect(all('downloads-empty')).toHaveLength(1);
        expect(el('job-card')).toBeNull();
      },
    );

    it('offers "Cargar más" per filter, with the cursor of that filter', async () => {
      await click('filter-completed');
      answer('completed', page([jobAt('c2', at(5), { status: 'completed' })], 'c2'));
      await settle();
      expect(el('load-more')?.textContent).toContain('Cargar más');

      await click('load-more');
      const req = http.expectOne((r) => r.url === '/api/jobs');
      expect(status(req.request)).toBe('completed');
      expect(req.request.params.get('before')).toBe('c2');
      expect((el('load-more') as HTMLButtonElement).disabled).toBe(true);
      req.flush(page([jobAt('c1', at(4), { status: 'completed' })]));
      await settle();

      expect(titles()).toEqual(['c2', 'c1']);
      expect(el('load-more')).toBeNull();

      // another filter has no older page of its own
      await click('filter-canceled');
      answer('canceled', page([]));
      await settle();
      expect(el('load-more')).toBeNull();
    });

    it('goes back to "Todas" when a download is enqueued under a filter that hides it', async () => {
      await click('filter-failed');
      answer('failed,interrupted', page([jobAt('f', at(15), { status: 'failed' })]));
      await settle();
      expect(titles()).toEqual(['f']);

      jobs.connect();
      FakeEventSource.instances[0].emit(
        'job.updated',
        jobAt('new', at(16, 14), { status: 'queued' }),
      );
      await settle();
      // "Todas" was never loaded in this test: it asks for its first page
      http.match((r) => r.url === '/api/jobs');

      expect(el('filter-all')?.getAttribute('aria-pressed')).toBe('true');
      expect(titles()).toEqual(['new', 'f']);
    });
  });

  describe('days', () => {
    it('heads the list with "Hoy", "Ayer" and the short date, newest first', async () => {
      jobs.jobs.set([
        jobAt('today', at(16, 9), { status: 'completed' }),
        jobAt('yesterday', at(15, 23), { status: 'completed' }),
        jobAt('week', at(9, 10), { status: 'completed' }),
        jobAt('also-week', at(9, 8), { status: 'completed' }),
        jobAt('old', at(12, 10, 3), { status: 'completed' }),
      ]);
      await settle();

      expect(headers()).toEqual(['Hoy', 'Ayer', '9 nov', '12 mar']);
      const days = all('day-group');
      expect(
        days.map((d) =>
          Array.from(d.querySelectorAll('[data-testid=job-title]')).map((t) =>
            t.textContent?.trim(),
          ),
        ),
      ).toEqual([['today'], ['yesterday'], ['week', 'also-week'], ['old']]);
    });

    it('adds the year only when it is not the current one', async () => {
      jobs.jobs.set([
        jobAt('now', at(10, 12, 11, 2026), { status: 'completed' }),
        jobAt('last-year', at(31, 12, 12, 2025), { status: 'completed' }),
      ]);
      await settle();

      expect(headers()).toEqual(['10 nov', '31 dic 2025']);
    });

    it('cuts the days at local midnight', async () => {
      jobs.jobs.set([
        jobAt('after', localIso(2026, 11, 16, 0, 5), { status: 'completed' }),
        jobAt('before', localIso(2026, 11, 15, 23, 55), { status: 'completed' }),
        jobAt('long-ago', localIso(2026, 11, 14, 23, 55), { status: 'completed' }),
      ]);
      await settle();

      expect(headers()).toEqual(['Hoy', 'Ayer', '14 nov']);
    });

    it('has non-collapsible headings: plain text, no button', async () => {
      jobs.jobs.set([jobAt('a', at(16, 9), { status: 'completed' })]);
      await settle();

      expect(el('day-header')?.querySelector('button')).toBeNull();
      expect(el('day-header')?.tagName).toBe('H3');
    });

    it('shows a Batch as one card under the day of its most recent job', async () => {
      const inBatch = (id: string, n: number, createdAt: string) =>
        jobAt(id, createdAt, {
          status: 'completed',
          batchId: 'b1',
          batchTitle: 'Mi lista',
          batchEntryCount: 3,
          playlistIndex: n,
        });
      jobs.jobs.set([
        inBatch('b3', 3, at(16, 11)),
        jobAt('solo', at(16, 10), { status: 'completed' }),
        inBatch('b2', 2, at(15, 20)),
        inBatch('b1', 1, at(15, 19)),
        jobAt('older', at(15, 8), { status: 'completed' }),
      ]);
      await settle();

      expect(headers()).toEqual(['Hoy', 'Ayer']);
      const [today, yesterday] = all('day-group');
      expect(today.querySelectorAll('[data-testid=batch]')).toHaveLength(1);
      expect(yesterday.querySelectorAll('[data-testid=batch]')).toHaveLength(0);
      expect(all('batch')).toHaveLength(1);
      expect(
        Array.from(today.querySelectorAll('[data-testid=batch] [data-testid=job-title]')).map((t) =>
          t.textContent?.trim(),
        ),
      ).toEqual(['b1', 'b2', 'b3']);
      expect(titles()).toEqual(['b1', 'b2', 'b3', 'solo', 'older']);
    });

    it('keeps a job under the day it was created when it finishes later', async () => {
      jobs.jobs.set([jobAt('a', at(15, 23), { status: 'downloading' })]);
      await settle();
      expect(headers()).toEqual(['Ayer']);

      jobs.jobs.set([jobAt('a', at(15, 23), { status: 'completed', finishedAt: at(16, 1) })]);
      await settle();

      expect(headers()).toEqual(['Ayer']);
    });
  });

  describe('removing from the History', () => {
    const batchJob = (id: string, n: number, state: Job['status']) =>
      jobAt(id, at(16, 10 + n), {
        status: state,
        batchId: 'b1',
        batchTitle: 'Mi lista',
        batchEntryCount: 4,
        playlistIndex: n,
      });
    const dialog = () => el('confirm-dialog') as HTMLDialogElement;
    const openBatchMenu = async () => {
      await click('batch-menu');
      await click('remove-batch');
    };
    const openHistoryMenu = async () => {
      await click('history-menu');
      await click('clear-history');
    };
    const key = (target: Element, name: string) =>
      target.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true }));

    beforeEach(async () => {
      document.body.appendChild(root());
      jobs.jobs.set([
        batchJob('b3', 3, 'downloading'),
        batchJob('b2', 2, 'failed'),
        batchJob('b1', 1, 'completed'),
        jobAt('solo', at(16, 9), { status: 'completed' }),
      ]);
      await settle();
    });

    describe('a Batch', () => {
      it('has a "⋮" menu with "Quitar del historial"', async () => {
        await click('batch-menu');

        expect(el('batch-menu')?.getAttribute('aria-expanded')).toBe('true');
        expect(el('remove-batch')?.textContent?.trim()).toBe('Quitar del historial');
        expect(document.activeElement).toBe(el('remove-batch'));
        expect(dialog().hasAttribute('open')).toBe(false);
      });

      it('is disabled while the Batch has no finished job', async () => {
        jobs.jobs.set([batchJob('b1', 1, 'downloading'), batchJob('b2', 2, 'queued')]);
        await settle();

        expect((el('batch-menu') as HTMLButtonElement).disabled).toBe(true);
      });

      it('asks first, with the number of finished jobs of the Batch and the files staying', async () => {
        await openBatchMenu();

        expect(dialog().hasAttribute('open')).toBe(true);
        expect(dialog().getAttribute('aria-labelledby')).toBe(el('confirm-title')!.id);
        expect(dialog().getAttribute('aria-describedby')).toBe(el('confirm-text')!.id);
        expect(el('confirm-title')?.textContent?.trim()).toBe('¿Quitar 2 descargas del historial?');
        expect(el('confirm-text')?.textContent?.trim()).toBe(
          'Los archivos descargados no se borran.',
        );
        expect(el('confirm-no')?.textContent?.trim()).toBe('Cancelar');
        expect(el('confirm-yes')?.textContent?.trim()).toBe('Quitar');
        expect(document.activeElement).toBe(el('confirm-no'));
        http.expectNone('/api/batches/b1');
        expect(el('remove-batch')).toBeNull(); // the menu closed
      });

      it('speaks of one download in the singular', async () => {
        jobs.jobs.set([batchJob('b1', 1, 'completed'), batchJob('b2', 2, 'downloading')]);
        await settle();
        await openBatchMenu();

        expect(el('confirm-title')?.textContent?.trim()).toBe('¿Quitar 1 descarga del historial?');
      });

      it('counts the finished jobs it knows even when the filter hides some', async () => {
        await click('filter-failed');
        http.match((r) => r.url === '/api/jobs');
        await openBatchMenu();

        expect(titles()).toEqual(['b2']);
        expect(el('confirm-title')?.textContent?.trim()).toBe('¿Quitar 2 descargas del historial?');
      });

      it('removes the finished jobs with DELETE /api/batches/{id} and keeps the running ones', async () => {
        await openBatchMenu();
        await click('confirm-yes');

        expect(dialog().hasAttribute('open')).toBe(false);
        const req = http.expectOne('/api/batches/b1');
        expect(req.request.method).toBe('DELETE');
        expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
        expect(titles()).toHaveLength(4); // nothing is dropped before the answer
        req.flush({ removed: 2 });
        await settle();

        expect(titles()).toEqual(['b3', 'solo']);
        expect(all('batch')).toHaveLength(1);
        expect(el('action-message')).toBeNull();
      });

      it('takes the focus to the filters when the card that had it is gone', async () => {
        jobs.jobs.set([batchJob('b1', 1, 'completed'), batchJob('b2', 2, 'failed')]);
        await settle();
        await openBatchMenu();
        await click('confirm-yes');
        http.expectOne('/api/batches/b1').flush({ removed: 2 });
        await settle();

        expect(all('batch')).toHaveLength(0);
        expect(document.activeElement).toBe(el('filter-all'));
      });

      it('does nothing on "Cancelar" and gives the focus back to the "⋮"', async () => {
        await openBatchMenu();
        await click('confirm-no');

        expect(dialog().hasAttribute('open')).toBe(false);
        http.expectNone('/api/batches/b1');
        expect(titles()).toHaveLength(4);
        expect(document.activeElement).toBe(el('batch-menu'));
      });

      it('does nothing on Esc and gives the focus back to the "⋮"', async () => {
        await openBatchMenu();
        key(dialog(), 'Escape');
        await settle();

        expect(dialog().hasAttribute('open')).toBe(false);
        http.expectNone('/api/batches/b1');
        expect(titles()).toHaveLength(4);
        expect(document.activeElement).toBe(el('batch-menu'));
      });

      it('does nothing on a click outside the dialog', async () => {
        await openBatchMenu();
        dialog().click();
        await settle();

        expect(dialog().hasAttribute('open')).toBe(false);
        http.expectNone('/api/batches/b1');
      });

      it('shows the usual error when the server refuses, and the real state', async () => {
        await openBatchMenu();
        await click('confirm-yes');
        http
          .expectOne('/api/batches/b1')
          .flush({ code: 'batch_not_found', message: 'x' }, { status: 404, statusText: 'x' });
        http.match((r) => r.url === '/api/jobs').forEach((r) => r.flush(page([])));
        await settle();

        expect(el('action-message')?.textContent).toContain('No se pudo completar la acción');
        expect(el('action-message')?.getAttribute('role')).toBe('alert');
      });
    });

    describe('the whole History', () => {
      it('has a "⋮" menu in the filter row with "Vaciar historial"', async () => {
        await click('history-menu');

        expect(el('filters')!.parentElement!.contains(el('history-menu'))).toBe(true);
        expect(el('filters')!.contains(el('history-menu'))).toBe(false);
        expect(el('clear-history')?.textContent?.trim()).toBe('Vaciar historial');
        expect(el('clear-history')?.getAttribute('role')).toBe('menuitem');
      });

      it('closes the menu with Esc and gives the focus back to the "⋮"', async () => {
        await click('history-menu');
        expect(document.activeElement).toBe(el('clear-history'));

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
        await settle();

        expect(el('clear-history')).toBeNull();
        expect(document.activeElement).toBe(el('history-menu'));
      });

      it('asks first, saying that the files stay', async () => {
        await openHistoryMenu();

        expect(dialog().hasAttribute('open')).toBe(true);
        expect(el('confirm-title')?.textContent?.trim()).toBe('¿Vaciar el historial?');
        expect(el('confirm-text')?.textContent?.trim()).toBe(
          'Se quitan todas las descargas terminadas. Los archivos descargados no se borran.',
        );
        expect(el('confirm-no')?.textContent?.trim()).toBe('Cancelar');
        expect(el('confirm-yes')?.textContent?.trim()).toBe('Vaciar');
        http.expectNone('/api/history');
      });

      it('empties it with DELETE /api/history and keeps the jobs in progress', async () => {
        await openHistoryMenu();
        await click('confirm-yes');

        const req = http.expectOne('/api/history');
        expect(req.request.method).toBe('DELETE');
        expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
        req.flush({ removed: 3 });
        await settle();

        expect(titles()).toEqual(['b3']);
        expect(document.activeElement).toBe(el('history-menu'));
      });

      it('shows the empty state once nothing is left', async () => {
        jobs.jobs.set([jobAt('a', at(16, 9), { status: 'completed' })]);
        await settle();
        await openHistoryMenu();
        await click('confirm-yes');
        http.expectOne('/api/history').flush({ removed: 1 });
        await settle();

        expect(el('downloads-empty')?.textContent?.trim()).toBe('No hay descargas.');
      });

      it('does nothing on "Cancelar"', async () => {
        await openHistoryMenu();
        await click('confirm-no');

        http.expectNone('/api/history');
        expect(titles()).toHaveLength(4);
        expect(document.activeElement).toBe(el('history-menu'));
      });

      it('does nothing on Esc', async () => {
        await openHistoryMenu();
        key(dialog(), 'Escape');
        await settle();

        expect(dialog().hasAttribute('open')).toBe(false);
        http.expectNone('/api/history');
        expect(titles()).toHaveLength(4);
        expect(document.activeElement).toBe(el('history-menu'));
      });

      it('shows the usual error when the server fails, and keeps the list', async () => {
        await openHistoryMenu();
        await click('confirm-yes');
        http.expectOne('/api/history').flush({}, { status: 500, statusText: 'x' });
        http.match((r) => r.url === '/api/jobs').forEach((r) => r.flush(page([])));
        await settle();

        expect(el('action-message')?.textContent).toContain('No se pudo completar la acción');
      });
    });

    it('drops what another tab removed (jobs.removed)', async () => {
      jobs.connect();
      FakeEventSource.instances[0].emit('jobs.removed', { ids: ['b1', 'b2', 'solo'] });
      await settle();

      expect(titles()).toEqual(['b3']);
    });
  });
});

describe('formatBytes', () => {
  it.each([
    [0, '0 B'],
    [512, '512 B'],
    [1536, '1,5 KB'],
    [5 * 1024 * 1024, '5,0 MB'],
    [3.25 * 1024 ** 3, '3,3 GB'],
  ])('%d -> %s', (bytes, text) => {
    expect(formatBytes(bytes)).toBe(text);
  });
});
