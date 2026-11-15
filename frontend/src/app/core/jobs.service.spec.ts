import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { FakeEventSource } from '../../testing/fake-event-source';
import { appHeaderInterceptor } from './api.interceptor';
import { EVENT_SOURCE_FACTORY } from './event-stream.service';
import { EnqueueError, Job, JobsService } from './jobs.service';

export const JOB: Job = {
  id: 'job1',
  batchId: null,
  playlistIndex: null,
  url: 'https://www.youtube.com/watch?v=jNQXAC9IVRw',
  title: 'Me at the zoo',
  mode: 'video',
  quality: 'best',
  audioFormat: null,
  status: 'queued',
  progressPercent: 0,
  downloadedBytes: null,
  totalBytes: null,
  speed: null,
  eta: null,
  outputPath: null,
  error: null,
  attempt: 1,
  createdAt: '2026-11-15T12:00:00.000000+00:00',
  startedAt: null,
  finishedAt: null,
};

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

  it('rehydrates from GET /api/jobs on every (re)connect', () => {
    service.connect();
    service.connect();
    expect(FakeEventSource.instances).toHaveLength(1);

    stream().open();
    const first = http.expectOne((r) => r.url === '/api/jobs');
    expect(first.request.params.get('limit')).toBe('200');
    first.flush({ jobs: [JOB], nextBefore: null });
    expect(service.jobs().map((j) => j.id)).toEqual(['job1']);

    // the connection dropped; the job finished in the meantime
    stream().open();
    http
      .expectOne((r) => r.url === '/api/jobs')
      .flush({ jobs: [{ ...JOB, status: 'completed' }], nextBefore: null });
    expect(service.jobs()[0].status).toBe('completed');
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

  it('enqueues a video with the app header and adds the job to the list', () => {
    let result: Job[] = [];
    service.enqueue(JOB.url, '480p', 'Me at the zoo').subscribe((jobs) => (result = jobs));

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

  it('omits the title when there is none', () => {
    service.enqueue(JOB.url, 'best', null).subscribe();

    const req = http.expectOne('/api/jobs');
    expect(req.request.body).toEqual({ url: JOB.url, mode: 'video', quality: 'best' });
    req.flush({ batchId: null, jobs: [JOB] });
  });

  it('turns API errors into EnqueueError with the code', () => {
    let error: unknown;
    service.enqueue(JOB.url, 'best', null).subscribe({ error: (e) => (error = e) });

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
    service.enqueue(JOB.url, 'best', null).subscribe({ error: (e) => (error = e) });

    http.expectOne('/api/jobs').error(new ProgressEvent('error'));

    expect((error as EnqueueError).code).toBe('network');
  });
});
