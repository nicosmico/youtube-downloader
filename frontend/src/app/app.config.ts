import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, ErrorHandler, provideBrowserGlobalErrorListeners } from '@angular/core';
import { appHeaderInterceptor } from './core/api.interceptor';
import { AppErrorHandler, errorLogInterceptor } from './core/error-log.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    { provide: ErrorHandler, useClass: AppErrorHandler },
    provideHttpClient(withInterceptors([appHeaderInterceptor, errorLogInterceptor])),
  ],
};
