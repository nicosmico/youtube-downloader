import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { App } from './app';
import { appHeaderInterceptor } from './core/api.interceptor';

const HEALTH = {
  app: 'youtube-downloader',
  version: '0.1.0',
  engine: { status: 'missing' },
  port: 4321,
};

describe('App', () => {
  let fixture: ComponentFixture<App>;
  let http: HttpTestingController;

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const button = () => (fixture.nativeElement as HTMLElement).querySelector('button') as HTMLButtonElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(withInterceptors([appHeaderInterceptor])),
        provideHttpClientTesting(),
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(App);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('shows the title and the Engine status from /api/health', async () => {
    http.expectOne('/api/health').flush(HEALTH);
    await fixture.whenStable();

    expect(text()).toContain('YouTube Downloader');
    expect(text()).toContain('No instalado');
    expect(text()).toContain('4321');
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
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
  });
});
