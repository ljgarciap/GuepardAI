import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from '../services/auth.service';
import { environment } from '../../environments/environment';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let authService: AuthService;
  const API = environment.apiUrl;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('attaches the Bearer token when the user is authenticated', () => {
    (authService as any).accessToken = 'token-abc';

    http.get(`${API}/brands`).subscribe();

    const req = httpMock.expectOne(`${API}/brands`);
    expect(req.request.headers.get('Authorization')).toBe('Bearer token-abc');
    req.flush([]);
  });

  it('does not attach a stale token to the login endpoint', () => {
    (authService as any).accessToken = 'token-abc';

    http.post(`${API}/auth/login`, { email: 'a@b.com', password: 'x' }).subscribe();

    const req = httpMock.expectOne(`${API}/auth/login`);
    expect(req.request.headers.has('Authorization')).toBeFalse();
    req.flush({ access_token: 't', refresh_token: 'r', token_type: 'bearer' });
  });

  it('deduplicates the refresh call across N concurrent 401s and retries every original request', () => {
    (authService as any).accessToken = 'expired-token';
    localStorage.setItem('guepard_refresh_token', 'refresh-456');

    let firstOk = false;
    let secondOk = false;
    http.get(`${API}/brands`).subscribe(() => (firstOk = true));
    http.get(`${API}/library/images`).subscribe(() => (secondOk = true));

    const req1 = httpMock.expectOne(`${API}/brands`);
    const req2 = httpMock.expectOne(`${API}/library/images`);
    req1.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });
    req2.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    // Solo UNA request de refresh, aunque dos requests originales dieron 401.
    const refreshReq = httpMock.expectOne(`${API}/auth/refresh`);
    refreshReq.flush({ access_token: 'new-token', refresh_token: 'new-refresh', token_type: 'bearer' });

    const retry1 = httpMock.expectOne(`${API}/brands`);
    expect(retry1.request.headers.get('Authorization')).toBe('Bearer new-token');
    retry1.flush([]);

    const retry2 = httpMock.expectOne(`${API}/library/images`);
    expect(retry2.request.headers.get('Authorization')).toBe('Bearer new-token');
    retry2.flush([]);

    expect(firstOk).toBeTrue();
    expect(secondOk).toBeTrue();
  });

  it('logs out and propagates the error when the refresh itself fails', () => {
    (authService as any).accessToken = 'expired-token';
    localStorage.setItem('guepard_refresh_token', 'refresh-456');
    const logoutSpy = spyOn(authService, 'logout');

    let errored = false;
    http.get(`${API}/brands`).subscribe({ error: () => (errored = true) });

    const req = httpMock.expectOne(`${API}/brands`);
    req.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    const refreshReq = httpMock.expectOne(`${API}/auth/refresh`);
    refreshReq.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    expect(logoutSpy).toHaveBeenCalled();
    expect(errored).toBeTrue();
  });
});
