import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { EngineInfo } from './engine.service';

export interface Health {
  app: string;
  version: string;
  engine: EngineInfo;
  port: number;
}

@Injectable({ providedIn: 'root' })
export class SystemService {
  private readonly http = inject(HttpClient);

  health(): Observable<Health> {
    return this.http.get<Health>('/api/health');
  }

  shutdown(): Observable<unknown> {
    return this.http.post('/api/system/shutdown', null);
  }
}
