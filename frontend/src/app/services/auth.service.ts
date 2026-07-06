import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, of, switchMap, tap, catchError, throwError, finalize, shareReplay } from 'rxjs';
import { environment } from '../../environments/environment';

export interface AuthUser {
  id: number;
  email: string;
  role: string;
  tenant_id: number | null;
  is_active: number;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

const REFRESH_TOKEN_KEY = 'guepard_refresh_token';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private apiUrl = environment.apiUrl;

  // Access token vive solo en memoria (nunca en localStorage) para acotar la
  // ventana de exposición ante XSS; el refresh token sí va en localStorage
  // porque el browser no puede setear cookies httpOnly desde JS.
  // Tradeoff documentado: docs/designs/autenticacion-multitenant-design.md §Frontend
  private accessToken: string | null = null;
  private refreshInProgress$: Observable<TokenResponse> | null = null;

  private currentUserSubject = new BehaviorSubject<AuthUser | null>(null);
  readonly currentUser$ = this.currentUserSubject.asObservable();

  constructor(private http: HttpClient, private router: Router) {}

  get currentUser(): AuthUser | null {
    return this.currentUserSubject.value;
  }

  getAccessToken(): string | null {
    return this.accessToken;
  }

  isAuthenticated(): boolean {
    return this.accessToken !== null;
  }

  login(email: string, password: string): Observable<AuthUser> {
    return this.http.post<TokenResponse>(`${this.apiUrl}/auth/login`, { email, password }).pipe(
      tap((tokens) => this.setTokens(tokens)),
      switchMap(() => this.fetchCurrentUser())
    );
  }

  register(email: string, password: string, tenantName?: string): Observable<AuthUser> {
    return this.http.post<TokenResponse>(`${this.apiUrl}/auth/register`, {
      email,
      password,
      tenant_name: tenantName || null,
    }).pipe(
      tap((tokens) => this.setTokens(tokens)),
      switchMap(() => this.fetchCurrentUser())
    );
  }

  /**
   * Intenta restaurar la sesión con el refresh token guardado (si existe) al
   * arrancar la app — el access token en memoria no sobrevive un reload.
   */
  restoreSession(): Observable<AuthUser | null> {
    if (!localStorage.getItem(REFRESH_TOKEN_KEY)) {
      return of(null);
    }
    return this.refreshAccessToken().pipe(
      switchMap(() => this.fetchCurrentUser()),
      catchError(() => {
        this.clearSession();
        return of(null);
      })
    );
  }

  /**
   * Single-flight: N llamadas concurrentes (ej. varios 401 del interceptor)
   * comparten la misma request de refresh en vez de disparar N.
   */
  refreshAccessToken(): Observable<TokenResponse> {
    if (this.refreshInProgress$) {
      return this.refreshInProgress$;
    }
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) {
      return throwError(() => new Error('No refresh token available'));
    }
    this.refreshInProgress$ = this.http
      .post<TokenResponse>(`${this.apiUrl}/auth/refresh`, { refresh_token: refreshToken })
      .pipe(
        tap((tokens) => this.setTokens(tokens)),
        shareReplay(1),
        finalize(() => { this.refreshInProgress$ = null; })
      );
    return this.refreshInProgress$;
  }

  logout(): void {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    this.clearSession();
    if (refreshToken) {
      // Best-effort: revoca el refresh token en el servidor, pero el logout
      // local ya ocurrió aunque esta llamada falle (ej. backend caído).
      this.http.post(`${this.apiUrl}/auth/logout`, { refresh_token: refreshToken }).subscribe({ error: () => {} });
    }
    this.router.navigate(['/login']);
  }

  private fetchCurrentUser(): Observable<AuthUser> {
    return this.http.get<AuthUser>(`${this.apiUrl}/auth/me`).pipe(
      tap((user) => this.currentUserSubject.next(user))
    );
  }

  private setTokens(tokens: TokenResponse): void {
    this.accessToken = tokens.access_token;
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  }

  private clearSession(): void {
    this.accessToken = null;
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    this.currentUserSubject.next(null);
  }
}
