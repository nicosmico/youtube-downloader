import { HttpInterceptorFn } from '@angular/common/http';

export const APP_HEADER_NAME = 'X-Requested-With';
export const APP_HEADER_VALUE = 'youtube-downloader';

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

/** The backend requires this header on every mutating request (see "Seguridad local"). */
export const appHeaderInterceptor: HttpInterceptorFn = (req, next) => {
  if (SAFE_METHODS.has(req.method.toUpperCase())) {
    return next(req);
  }
  return next(req.clone({ setHeaders: { [APP_HEADER_NAME]: APP_HEADER_VALUE } }));
};
