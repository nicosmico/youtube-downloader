import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FakeEventSource } from '../../testing/fake-event-source';
import { appHeaderInterceptor } from '../core/api.interceptor';
import { EVENT_SOURCE_FACTORY } from '../core/event-stream.service';
import { JOB } from '../../testing/fixtures';
import { Job, JobsService } from '../core/jobs.service';
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
  const show = async (...list: Partial<Job>[]) => {
    jobs.jobs.set(list.map((j, i) => ({ ...JOB, id: `job${i}`, ...j })));
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

  it('says there is nothing yet', () => {
    expect(el('downloads-empty')?.textContent).toContain('Todavía no hay descargas');
    expect(all('job-card')).toHaveLength(0);
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
  ] as const)('shows what was requested: %j', async (options, label) => {
    await show({ ...options });

    expect(el('job-options')?.textContent?.trim()).toBe(label);
  });

  it('uses a generic title when the job has none', async () => {
    await show({ title: null });

    expect(el('job-title')?.textContent).toContain('Video de YouTube');
  });

  it('shows progress, bytes, speed and ETA while downloading', async () => {
    await show({
      status: 'downloading',
      progressPercent: 41.6,
      downloadedBytes: 5 * 1024 * 1024,
      totalBytes: 12 * 1024 * 1024,
      speed: 2.5 * 1024 * 1024,
      eta: 75,
    });

    expect(el('job-status')?.textContent).toContain('Descargando');
    expect((el('job-progress') as HTMLProgressElement).value).toBe(42);
    expect(el('job-percent')?.textContent).toContain('42%');
    expect(el('job-bytes')?.textContent).toContain('5,0 MB / 12,0 MB');
    expect(el('job-speed')?.textContent).toContain('2,5 MB/s');
    expect(el('job-eta')?.textContent).toContain('Quedan 1:15');
  });

  it('copes with unknown totals, speed and ETA', async () => {
    await show({ status: 'downloading', downloadedBytes: 2048, totalBytes: null });

    expect(el('job-bytes')?.textContent).toContain('2,0 KB');
    expect(el('job-bytes')?.textContent).not.toContain('/');
    expect(el('job-speed')).toBeNull();
    expect(el('job-eta')).toBeNull();
  });

  it('shows a full bar without speed or ETA while processing', async () => {
    await show({
      status: 'processing',
      progressPercent: 99,
      downloadedBytes: 1024,
      totalBytes: 1024,
      speed: 1000,
      eta: 3,
    });

    expect(el('job-status')?.textContent).toContain('Procesando');
    expect((el('job-progress') as HTMLProgressElement).value).toBe(100);
    expect(el('job-speed')).toBeNull();
    expect(el('job-eta')).toBeNull();
  });

  it('offers "Abrir carpeta" on a completed job and shows the result', async () => {
    await show({ status: 'completed', progressPercent: 100 });
    expect(el('job-status')?.textContent).toContain('Completada');
    expect(el('job-progress')).toBeNull();

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

    expect(el('job-status')?.textContent).toContain('Fallida');
    expect(el('job-error')?.textContent).toContain('El video no está disponible.');
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
  });

  it('shows the queue counts from queue.updated and follows the jobs without a reload', async () => {
    jobs.connect();
    const stream = FakeEventSource.instances[0];
    expect(el('queue-summary')).toBeNull();

    for (const id of ['a', 'b', 'c']) {
      stream.emit('job.updated', {
        ...JOB,
        id,
        createdAt: `2026-11-15T12:00:0${id === 'a' ? 1 : id === 'b' ? 2 : 3}.000000+00:00`,
      });
    }
    stream.emit('queue.updated', { active: 0, queued: 3 });
    await settle();
    expect(el('queue-summary')?.textContent).toMatch(/0 activas\s*·\s*3 en cola/);
    expect(all('job-status').map((s) => s.textContent?.trim())).toEqual([
      'En cola',
      'En cola',
      'En cola',
    ]);

    // two slots are taken: the oldest two start, the newest keeps waiting
    stream.emit('job.updated', {
      ...JOB,
      id: 'a',
      createdAt: '2026-11-15T12:00:01.000000+00:00',
      status: 'downloading',
    });
    stream.emit('job.updated', {
      ...JOB,
      id: 'b',
      createdAt: '2026-11-15T12:00:02.000000+00:00',
      status: 'downloading',
    });
    stream.emit('queue.updated', { active: 2, queued: 1 });
    await settle();
    expect(el('queue-summary')?.textContent).toMatch(/2 activas\s*·\s*1 en cola/);
    expect(all('job-status').map((s) => s.textContent?.trim())).toEqual([
      'En cola',
      'Descargando',
      'Descargando',
    ]);

    stream.emit('queue.updated', { active: 0, queued: 0 });
    await settle();
    expect(el('queue-summary')).toBeNull();
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

    stream.emit('job.updated', { ...JOB, status: 'downloading', progressPercent: 10 });
    await settle();

    expect(all('job-card')).toHaveLength(2);
    expect(all('job-status')[1].textContent).toContain('Descargando');
    expect(all('job-card')[1].getAttribute('data-status')).toBe('downloading');
  });

  it('rehydrates on reconnect', async () => {
    jobs.connect();
    FakeEventSource.instances[0].open();
    http
      .expectOne((r) => r.url === '/api/jobs')
      .flush({ jobs: [{ ...JOB, status: 'failed', error: 'Falló.' }], nextBefore: null });
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
      batchJob(1, { id: 'a', status: 'completed' }),
      batchJob(2, { id: 'b', status: 'downloading', progressPercent: 40 }),
    );

    expect(all('batch')).toHaveLength(1);
    expect(all('batch-title')[0].textContent).toContain('Mi playlist');
    expect(all('batch-summary')[0].textContent).toContain('1/3 completadas');
    expect(all('batch-summary')[0].textContent).toContain('1 en curso');
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
      'Completada',
      'Fallida',
      'Completada',
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
