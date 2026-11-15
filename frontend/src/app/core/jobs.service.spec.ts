import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { FakeEventSource } from '../../testing/fake-event-source';
import { appHeaderInterceptor } from './api.interceptor';
import { EVENT_SOURCE_FACTORY } from './event-stream.service';
import { EnqueueError, Job, JobsService } from './jobs.service';
import { JOB } from '../../testing/fixtures';
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
    expect(service.hasMoreHistory()).toBe(true);

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
    expect(service.hasMoreHistory()).toBe(false);
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
    expect(service.hasMoreHistory()).toBe(true);
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
});
