import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';

export interface TosStatus {
  accepted: boolean;
  current_version: string;
  accepted_version: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
}

@Injectable({ providedIn: 'root' })
export class TosService {
  private apiUrl = environment.apiUrl;

  private statusSubject = new BehaviorSubject<TosStatus | null>(null);
  readonly status$ = this.statusSubject.asObservable();

  constructor(private http: HttpClient) {}

  get currentStatus(): TosStatus | null {
    return this.statusSubject.value;
  }

  fetchStatus(): Observable<TosStatus> {
    return this.http.get<TosStatus>(`${this.apiUrl}/tos/status`).pipe(
      tap((s) => this.statusSubject.next(s))
    );
  }

  accept(): Observable<TosStatus> {
    return this.http.post<TosStatus>(`${this.apiUrl}/tos/accept`, {}).pipe(
      tap((s) => this.statusSubject.next(s))
    );
  }

  reject(): Observable<TosStatus> {
    return this.http.post<TosStatus>(`${this.apiUrl}/tos/reject`, {}).pipe(
      tap((s) => this.statusSubject.next(s))
    );
  }
}
