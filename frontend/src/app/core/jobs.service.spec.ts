import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { FakeEventSource } from '../../testing/fake-event-source';
import { appHeaderInterceptor } from './api.interceptor';
import { EVENT_SOURCE_FACTORY } from './event-stream.service';
import { EnqueueError, Job, JobsService } from './jobs.service';
import { JOB, jobAt } from '../../testing/fixtures';
import { flushRehydration } from '../../testing/rehydration';

describe('JobsService', () => {
  let service: JobsService;
  let http: HttpTestingController;

  const stream = () => FakeEventSource.instances[0];

  beforeEach(() => {
    FakeEventSource.reset();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
        { provide: EVENT_SOURCE_FACTORY, useValue: FakeEventSource.factory() },
      ],
    });
    service = TestBed.inject(JobsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('rehydrates the Queue and the History from GET /api/jobs on every (re)connect', () => {
    service.connect();
    service.connect();
    expect(FakeEventSource.instances).toHaveLength(1);

    stream().open();
    const requests = http.match((r) => r.url === '/api/jobs');
    const byStatus = (status: string) =>
      requests.find((r) => r.request.params.get('status') === status);
    expect(byStatus('queued,downloading,processing')?.request.params.get('limit')).toBe('200');
    expect(byStatus('completed,failed,canceled,interrupted')?.request.params.get('limit')).toBe(
      '50',
    );
    flushRehydration(http, { queue: [JOB] }, requests);
    expect(service.jobs().map((j) => j.id)).toEqual(['job1']);

    // the connection dropped; the job finished in the meantime
    stream().open();
    flushRehydration(http, { history: [{ ...JOB, status: 'completed' }] });
    expect(service.jobs()).toHaveLength(1);
    expect(service.jobs()[0].status).toBe('completed');
  });

  it('removes a job on job.removed', () => {
    service.connect();
    service.jobs.set([JOB, { ...JOB, id: 'job2', createdAt: '2026-11-15T12:00:05.000000+00:00' }]);

    stream().emit('job.removed', { id: 'job2' });

    expect(service.jobs().map((j) => j.id)).toEqual(['job1']);
  });

  it('loads older History pages with the cursor until there are no more', () => {
    service.connect();
    stream().open();
    const first = { ...JOB, id: 'h1', status: 'completed' as const };
    flushRehydration(http, { history: [first], nextBefore: 'h1' });
    expect(service.hasMore()).toBe(true);

    service.loadMore();
    service.loadMore(); // already loading: ignored
    const req = http.expectOne((r) => r.url === '/api/jobs');
    expect(req.request.params.get('before')).toBe('h1');
    expect(req.request.params.get('status')).toBe('completed,failed,canceled,interrupted');
    expect(service.loadingMore()).toBe(true);
    req.flush({
      jobs: [{ ...first, id: 'h0', createdAt: '2026-11-15T11:00:00.000000+00:00' }],
      nextBefore: null,
    });

    expect(service.jobs().map((j) => j.id)).toEqual(['h1', 'h0']);
    expect(service.hasMore()).toBe(false);
    expect(service.loadingMore()).toBe(false);
    service.loadMore();
    http.expectNone((r) => r.url === '/api/jobs');
  });

  it('starts the History over on reconnect (extra pages are dropped)', () => {
    service.connect();
    stream().open();
    flushRehydration(http, {
      history: [{ ...JOB, id: 'h1', status: 'completed' }],
      nextBefore: 'h1',
    });
    service.loadMore();
    http
      .expectOne((r) => r.url === '/api/jobs')
      .flush({
        jobs: [
          { ...JOB, id: 'h0', status: 'completed', createdAt: '2026-11-15T11:00:00.000000+00:00' },
        ],
        nextBefore: null,
      });

    stream().open();
    flushRehydration(http, {
      history: [{ ...JOB, id: 'h1', status: 'completed' }],
      nextBefore: 'h1',
    });

    expect(service.jobs().map((j) => j.id)).toEqual(['h1']);
    expect(service.hasMore()).toBe(true);
  });

  it('removes from the History with DELETE and takes the job out of the list', () => {
    service.jobs.set([{ ...JOB, status: 'completed' }]);
    service.remove(JOB.id).subscribe();

    const req = http.expectOne(`/api/jobs/${JOB.id}`);
    expect(req.request.method).toBe('DELETE');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ status: 'removed' });

    expect(service.jobs()).toEqual([]);
  });

  it('shows the truth again when the removal is refused (409)', () => {
    service.jobs.set([{ ...JOB, status: 'completed' }]);
    let error: unknown;
    service.remove(JOB.id).subscribe({ error: (e) => (error = e) });

    http
      .expectOne(`/api/jobs/${JOB.id}`)
      .flush({ code: 'job_not_removable', message: 'x' }, { status: 409, statusText: 'x' });
    flushRehydration(http, { queue: [{ ...JOB, status: 'queued' }] });

    expect((error as EnqueueError).code).toBe('job_not_removable');
    expect(service.jobs()[0].status).toBe('queued');
  });

  it('asks the server to reveal a file and surfaces its Spanish message on failure', () => {
    let error: unknown;
    service.reveal(JOB.id).subscribe({ error: (e) => (error = e) });

    const req = http.expectOne(`/api/jobs/${JOB.id}/reveal`);
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush(
      { code: 'file_missing', message: 'El archivo ya no está en su carpeta.' },
      { status: 404, statusText: 'x' },
    );

    expect((error as EnqueueError).code).toBe('file_missing');
    expect((error as EnqueueError).message).toBe('El archivo ya no está en su carpeta.');
  });

  it('applies job.updated: updates a job in place and adds new ones, newest first', () => {
    service.connect();
    stream().emit('job.updated', JOB);
    stream().emit('job.updated', {
      ...JOB,
      id: 'job2',
      createdAt: '2026-11-15T12:00:05.000000+00:00',
    });
    stream().emit('job.updated', { ...JOB, status: 'downloading', progressPercent: 42 });

    expect(service.jobs().map((j) => j.id)).toEqual(['job2', 'job1']);
    expect(service.jobs()[1]).toMatchObject({ status: 'downloading', progressPercent: 42 });
  });

  it('applies queue.updated, which is also the snapshot sent on connect', () => {
    service.connect();
    expect(service.queue()).toEqual({ active: 0, queued: 0 });

    stream().emit('queue.updated', { active: 2, queued: 3 });

    expect(service.queue()).toEqual({ active: 2, queued: 3 });
  });

  it('enqueues a video with the app header and adds the job to the list', () => {
    let result: Job[] = [];
    service
      .enqueue(JOB.url, { mode: 'video', quality: '480p' }, 'Me at the zoo')
      .subscribe((jobs) => (result = jobs));

    const req = http.expectOne('/api/jobs');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    expect(req.request.body).toEqual({
      url: JOB.url,
      mode: 'video',
      quality: '480p',
      title: 'Me at the zoo',
    });
    req.flush({ batchId: null, jobs: [JOB] });

    expect(result).toEqual([JOB]);
    expect(service.jobs()).toEqual([JOB]);
  });

  it('enqueues audio with its format and no quality', () => {
    service.enqueue(JOB.url, { mode: 'audio', audioFormat: 'opus' }, 'Me at the zoo').subscribe();

    const req = http.expectOne('/api/jobs');
    expect(req.request.body).toEqual({
      url: JOB.url,
      mode: 'audio',
      audioFormat: 'opus',
      title: 'Me at the zoo',
    });
    req.flush({
      batchId: null,
      jobs: [{ ...JOB, mode: 'audio', quality: null, audioFormat: 'opus' }],
    });
  });

  it('sends the thumbnail of the preview, and omits it when there is none', () => {
    service
      .enqueue(JOB.url, { mode: 'video', quality: 'best' }, 'T', undefined, JOB.thumbnail)
      .subscribe();
    const req = http.expectOne('/api/jobs');
    expect(req.request.body).toEqual({
      url: JOB.url,
      mode: 'video',
      quality: 'best',
      title: 'T',
      thumbnail: JOB.thumbnail,
    });
    req.flush({ batchId: null, jobs: [JOB] });

    service.enqueue(JOB.url, { mode: 'video', quality: 'best' }, 'T', [], null).subscribe();
    expect('thumbnail' in http.expectOne('/api/jobs').request.body).toBe(false);
  });

  it('omits the title when there is none', () => {
    service.enqueue(JOB.url, { mode: 'video', quality: 'best' }, null).subscribe();

    const req = http.expectOne('/api/jobs');
    expect(req.request.body).toEqual({ url: JOB.url, mode: 'video', quality: 'best' });
    req.flush({ batchId: null, jobs: [JOB] });
  });

  it('turns API errors into EnqueueError with the code', () => {
    let error: unknown;
    service
      .enqueue(JOB.url, { mode: 'video', quality: 'best' }, null)
      .subscribe({ error: (e) => (error = e) });

    http
      .expectOne('/api/jobs')
      .flush({ code: 'engine_not_ready', message: 'No listo' }, { status: 409, statusText: 'x' });

    expect(error).toBeInstanceOf(EnqueueError);
    expect((error as EnqueueError).code).toBe('engine_not_ready');
    expect((error as EnqueueError).message).toBe('No listo');
    expect(service.jobs()).toEqual([]);
  });

  it('reports a missing server as `network`', () => {
    let error: unknown;
    service
      .enqueue(JOB.url, { mode: 'video', quality: 'best' }, null)
      .subscribe({ error: (e) => (error = e) });

    http.expectOne('/api/jobs').error(new ProgressEvent('error'));

    expect((error as EnqueueError).code).toBe('network');
  });

  it('cancels a job with the app header and stores the result', () => {
    service.jobs.set([{ ...JOB, status: 'downloading' }]);
    let result: Job | undefined;
    service.cancel(JOB.id).subscribe((job) => (result = job));

    const req = http.expectOne(`/api/jobs/${JOB.id}/cancel`);
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
    req.flush({ ...JOB, status: 'canceled' });

    expect(result?.status).toBe('canceled');
    expect(service.jobs()[0].status).toBe('canceled');
  });

  it('retries a job and stores the new attempt', () => {
    service.jobs.set([{ ...JOB, status: 'failed' }]);
    service.retry(JOB.id).subscribe();

    const req = http.expectOne(`/api/jobs/${JOB.id}/retry`);
    expect(req.request.method).toBe('POST');
    req.flush({ ...JOB, status: 'queued', attempt: 2 });

    expect(service.jobs()[0]).toMatchObject({ status: 'queued', attempt: 2 });
  });

  it('reports the API code of a refused command and reloads the list', () => {
    let error: unknown;
    service.retry(JOB.id).subscribe({ error: (e) => (error = e) });

    http
      .expectOne(`/api/jobs/${JOB.id}/retry`)
      .flush({ code: 'job_not_retryable', message: 'No' }, { status: 409, statusText: 'x' });
    flushRehydration(http, { queue: [JOB] });

    expect((error as EnqueueError).code).toBe('job_not_retryable');
    expect(service.jobs()).toEqual([JOB]);
  });

  describe('arrival order of the HTTP response and the SSE event', () => {
    const DOWNLOADING = {
      ...JOB,
      status: 'downloading' as const,
      startedAt: '2026-11-15T12:00:01Z',
    };

    it('does not bring a job back to queued when job.updated arrived before the POST response', () => {
      service.connect();
      service.enqueue(JOB.url, { mode: 'video', quality: 'best' }, null).subscribe();
      const req = http.expectOne('/api/jobs');

      stream().emit('job.updated', DOWNLOADING);
      req.flush({ batchId: null, jobs: [JOB] });

      expect(service.jobs()).toHaveLength(1);
      expect(service.jobs()[0].status).toBe('downloading');
    });

    it('adds the job from the response and then applies the SSE update', () => {
      service.connect();
      service.enqueue(JOB.url, { mode: 'video', quality: 'best' }, null).subscribe();
      http.expectOne('/api/jobs').flush({ batchId: null, jobs: [JOB] });
      expect(service.jobs()[0].status).toBe('queued');

      stream().emit('job.updated', DOWNLOADING);

      expect(service.jobs()).toHaveLength(1);
      expect(service.jobs()[0].status).toBe('downloading');
    });

    it('keeps the SSE state of every job of a playlist enqueue', () => {
      service.connect();
      const second = { ...JOB, id: 'job2', createdAt: '2026-11-15T12:00:00.000001+00:00' };
      service.enqueue(JOB.url, { mode: 'video', quality: 'best' }, null, []).subscribe();
      const req = http.expectOne('/api/jobs');

      stream().emit('job.updated', DOWNLOADING);
      req.flush({ batchId: 'b1', jobs: [JOB, second] });

      expect(service.jobs().find((j) => j.id === 'job1')?.status).toBe('downloading');
      expect(service.jobs().find((j) => j.id === 'job2')?.status).toBe('queued');
    });

    it('does not bring a retried job back to queued when job.updated arrived first', () => {
      service.connect();
      service.jobs.set([{ ...JOB, status: 'failed' }]);
      service.retry(JOB.id).subscribe();
      const req = http.expectOne(`/api/jobs/${JOB.id}/retry`);

      stream().emit('job.updated', { ...DOWNLOADING, attempt: 2 });
      req.flush({ ...JOB, status: 'queued', attempt: 2 });

      expect(service.jobs()[0]).toMatchObject({ status: 'downloading', attempt: 2 });
    });

    it('applies the retry response first and then the SSE update', () => {
      service.connect();
      service.jobs.set([{ ...JOB, status: 'failed' }]);
      service.retry(JOB.id).subscribe();
      http.expectOne(`/api/jobs/${JOB.id}/retry`).flush({ ...JOB, status: 'queued', attempt: 2 });
      expect(service.jobs()[0]).toMatchObject({ status: 'queued', attempt: 2 });

      stream().emit('job.updated', { ...DOWNLOADING, attempt: 2 });

      expect(service.jobs()[0]).toMatchObject({ status: 'downloading', attempt: 2 });
    });
  });

  describe('filters', () => {
    const at = (n: number) => `2026-11-15T12:00:${String(n).padStart(2, '0')}.000000+00:00`;
    const done = (id: string, n: number) => jobAt(id, at(n), { status: 'completed' });
    const failed = (id: string, n: number) => jobAt(id, at(n), { status: 'failed' });
    const queued = (id: string, n: number) => jobAt(id, at(n), { status: 'queued' });
    const ids = () => service.visibleJobs().map((j) => j.id);
    const statusOf = (r: HttpRequest<unknown> | TestRequest) =>
      ('request' in r ? r.request : r).params.get('status');
    /** Connects and answers the rehydration with the given jobs on the first page of "Todas". */
    const connected = (answer: Parameters<typeof flushRehydration>[1]) => {
      service.connect();
      stream().open();
      flushRehydration(http, answer);
    };
    const page = (jobs: Job[], nextBefore: string | null = null) => ({ jobs, nextBefore });

    it('shows every job under "Todas", newest first, and a job keeps its place when it ends', () => {
      connected({
        queue: [queued('q', 5)],
        history: [done('h1', 4), failed('h2', 3)],
      });
      expect(service.filter()).toBe('all');
      expect(ids()).toEqual(['q', 'h1', 'h2']);

      stream().emit('job.updated', { ...queued('q', 5), status: 'downloading' });
      stream().emit('job.updated', { ...queued('q', 5), status: 'completed' });

      expect(ids()).toEqual(['q', 'h1', 'h2']);
    });

    it.each([
      ['active', ['q', 'd']],
      ['completed', ['c1', 'c2']],
      ['failed', ['f', 'i']],
      ['canceled', ['x']],
    ] as const)('"%s" shows only the statuses of its row', (filter, expected) => {
      service.jobs.set([
        queued('q', 9),
        jobAt('d', at(8), { status: 'downloading' }),
        done('c1', 7),
        failed('f', 6),
        jobAt('i', at(5), { status: 'interrupted' }),
        jobAt('x', at(4), { status: 'canceled' }),
        done('c2', 3),
      ]);
      service.select(filter);
      http.match((r) => r.url === '/api/jobs'); // the first page of the filter, not under test

      expect(ids()).toEqual(expected);
    });

    it.each([
      ['completed', 'completed'],
      ['failed', 'failed,interrupted'],
      ['canceled', 'canceled'],
    ] as const)('"%s" fetches its first page with status=%s, once', (filter, status) => {
      connected({});

      service.select(filter);
      const req = http.expectOne((r) => r.url === '/api/jobs');
      expect(statusOf(req)).toBe(status);
      expect(req.request.params.get('limit')).toBe('50');
      expect(req.request.params.has('before')).toBe(false);
      expect(service.loading()).toBe(true);
      req.flush(page([]));
      expect(service.loading()).toBe(false);

      service.select('all');
      service.select(filter);
      http.expectNone((r) => r.url === '/api/jobs');
    });

    it('"En curso" needs no request: the Queue is always loaded whole', () => {
      connected({ queue: [queued('q', 5)], history: [done('h', 4)] });

      service.select('active');

      http.expectNone((r) => r.url === '/api/jobs');
      expect(ids()).toEqual(['q']);
      expect(service.hasMore()).toBe(false);
    });

    it('never looks empty because its jobs sit on a page "Todas" has not loaded', () => {
      // the first page of "Todas" is all failures; the completed ones are further back
      connected({
        history: [failed('f1', 9), failed('f2', 8)],
        nextBefore: 'f2',
      });
      service.select('completed');
      expect(ids()).toEqual([]);
      expect(service.loading()).toBe(true);

      http
        .expectOne((r) => statusOf(r) === 'completed')
        .flush(page([done('c1', 2), done('c2', 1)]));

      expect(ids()).toEqual(['c1', 'c2']);
      expect(service.loading()).toBe(false);
    });

    it('pages each filter with its own cursor', () => {
      connected({ history: [done('h1', 9), failed('h2', 8)], nextBefore: 'h2' });
      service.select('completed');
      http
        .expectOne((r) => statusOf(r) === 'completed')
        .flush(page([done('c1', 7), done('c2', 6)], 'c2'));
      expect(service.hasMore()).toBe(true);

      service.loadMore();
      service.loadMore(); // already loading: ignored
      const req = http.expectOne((r) => r.url === '/api/jobs');
      expect(statusOf(req)).toBe('completed');
      expect(req.request.params.get('before')).toBe('c2');
      expect(req.request.params.get('limit')).toBe('50');
      expect(service.loadingMore()).toBe(true);
      req.flush(page([done('c3', 5)]));

      expect(ids()).toEqual(['h1', 'c1', 'c2', 'c3']);
      expect(service.hasMore()).toBe(false);

      // "Todas" still has its own next page
      service.select('all');
      expect(service.hasMore()).toBe(true);
      service.loadMore();
      const all = http.expectOne((r) => r.url === '/api/jobs');
      expect(statusOf(all)).toBe('completed,failed,canceled,interrupted');
      expect(all.request.params.get('before')).toBe('h2');
      all.flush(page([failed('h3', 4)]));
      expect(service.hasMore()).toBe(false);
    });

    it('does not show, under "Todas", jobs older than its own pages that another filter loaded', () => {
      connected({ history: [done('h1', 9), failed('h2', 8)], nextBefore: 'h2' });
      service.select('completed');
      http
        .expectOne((r) => statusOf(r) === 'completed')
        .flush(page([done('c1', 7), done('c2', 2)], 'c2'));

      service.select('all');

      // c1 and c2 are older than where "Todas" reaches: there could be failures between them
      expect(ids()).toEqual(['h1', 'h2']);
    });

    it('applies a job that ends under the filter it belongs to, and drops it from the others', () => {
      connected({ queue: [queued('q', 9)], history: [] });
      service.select('completed');
      http.expectOne((r) => statusOf(r) === 'completed').flush(page([]));
      expect(ids()).toEqual([]);

      stream().emit('job.updated', { ...queued('q', 9), status: 'completed' });
      expect(ids()).toEqual(['q']);

      stream().emit('job.updated', { ...queued('q', 9), status: 'failed' });
      expect(ids()).toEqual([]);
    });

    it('starts over on reconnect: only the current filter is fetched again', () => {
      connected({ history: [done('h1', 9)] });
      service.select('completed');
      http.expectOne((r) => statusOf(r) === 'completed').flush(page([done('c1', 5)], 'c1'));
      service.select('canceled');
      http.expectOne((r) => statusOf(r) === 'canceled').flush(page([]));

      stream().open();
      const requests = http.match((r) => r.url === '/api/jobs');
      expect(requests.map(statusOf).sort()).toEqual(['canceled', 'queued,downloading,processing']);
      requests.forEach((r) => r.flush(page([])));

      // the filters that were not showing are unloaded: selecting one fetches it again
      service.select('completed');
      http.expectOne((r) => statusOf(r) === 'completed').flush(page([]));
      expect(ids()).toEqual([]);
    });

    it('ignores the answer to a list that a reconnect replaced', () => {
      service.connect();
      stream().open();
      const stale = http.match((r) => r.url === '/api/jobs');

      stream().open();
      flushRehydration(http, { history: [done('new', 5)] });
      flushRehydration(http, { history: [done('old', 4)] }, stale);

      expect(ids()).toEqual(['new']);
    });

    it('moves the cursor when the job it points at is removed, so "Cargar más" does not end early', () => {
      connected({ history: [done('h1', 9), done('h2', 8)], nextBefore: 'h2' });

      stream().emit('job.removed', { id: 'h2' });
      service.loadMore();

      const req = http.expectOne((r) => r.url === '/api/jobs');
      expect(req.request.params.get('before')).toBe('h1');
      req.flush(page([]));
    });
  });

  describe('removing many', () => {
    const at = (n: number) => `2026-11-15T12:00:${String(n).padStart(2, '0')}.000000+00:00`;
    const inBatch = (id: string, n: number, status: Job['status']) =>
      jobAt(id, at(n), { status, batchId: 'b1', batchTitle: 'Lista', batchEntryCount: 4 });

    it('drops every id of jobs.removed', () => {
      service.connect();
      service.jobs.set([jobAt('a', at(3)), jobAt('b', at(2)), jobAt('c', at(1))]);

      stream().emit('jobs.removed', { ids: ['a', 'c', 'unknown'] });

      expect(service.jobs().map((j) => j.id)).toEqual(['b']);
    });

    it('removes the finished jobs of a Batch with DELETE /api/batches/{id} and drops them', () => {
      service.jobs.set([
        inBatch('a', 4, 'downloading'),
        inBatch('b', 3, 'completed'),
        inBatch('c', 2, 'failed'),
        jobAt('other', at(1), { status: 'completed' }),
      ]);
      let done = false;
      service.removeBatch('b1').subscribe(() => (done = true));

      const req = http.expectOne('/api/batches/b1');
      expect(req.request.method).toBe('DELETE');
      expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
      expect(service.jobs()).toHaveLength(4);
      req.flush({ removed: 2 });

      expect(done).toBe(true);
      expect(service.jobs().map((j) => j.id)).toEqual(['a', 'other']);
    });

    it('shows the truth again when removing a Batch fails', () => {
      service.jobs.set([inBatch('b', 3, 'completed')]);
      let error: unknown;
      service.removeBatch('b1').subscribe({ error: (e) => (error = e) });

      http
        .expectOne('/api/batches/b1')
        .flush({ code: 'batch_not_found', message: 'x' }, { status: 404, statusText: 'x' });
      flushRehydration(http, {});

      expect((error as EnqueueError).code).toBe('batch_not_found');
      expect(service.jobs()).toEqual([]);
    });

    it('empties the History with DELETE /api/history and keeps what is in progress', () => {
      service.connect();
      stream().open();
      flushRehydration(http, {
        queue: [jobAt('q', at(5), { status: 'queued' })],
        history: [
          jobAt('h1', at(4), { status: 'completed' }),
          jobAt('h2', at(3), { status: 'failed' }),
        ],
        nextBefore: 'h2',
      });
      expect(service.hasMore()).toBe(true);
      service.clearHistory().subscribe();

      const req = http.expectOne('/api/history');
      expect(req.request.method).toBe('DELETE');
      expect(req.request.headers.get('X-Requested-With')).toBe('youtube-downloader');
      req.flush({ removed: 2 });

      expect(service.jobs().map((j) => j.id)).toEqual(['q']);
      expect(service.hasMore()).toBe(false); // nothing finished is left on the server
    });

    it('shows the truth again when emptying the History fails', () => {
      service.jobs.set([jobAt('h', at(1), { status: 'completed' })]);
      let failed = false;
      service.clearHistory().subscribe({ error: () => (failed = true) });

      http.expectOne('/api/history').flush({}, { status: 500, statusText: 'x' });
      flushRehydration(http, { history: [jobAt('h', at(1), { status: 'completed' })] });

      expect(failed).toBe(true);
      expect(service.jobs().map((j) => j.id)).toEqual(['h']);
    });
  });
});
