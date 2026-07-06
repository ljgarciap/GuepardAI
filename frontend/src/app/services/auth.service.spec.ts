import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { AuthService } from './auth.service';
import { environment } from '../../environments/environment';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;
  let router: Router;
  const API = environment.apiUrl;

  const mockTokens = {
    access_token: 'access-123',
    refresh_token: 'refresh-456',
    token_type: 'bearer',
  };

  const mockUser = { id: 1, email: 'admin@guepardai.com', role: 'admin', tenant_id: 1, is_active: 1 };

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [AuthService, provideRouter([])],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('login()', () => {
    it('stores the access token in memory and the refresh token in localStorage, then fetches /me', () => {
      service.login('admin@guepardai.com', 'secret').subscribe((user) => {
        expect(user).toEqual(mockUser);
      });

      const loginReq = httpMock.expectOne(`${API}/auth/login`);
      expect(loginReq.request.method).toBe('POST');
      expect(loginReq.request.body).toEqual({ email: 'admin@guepardai.com', password: 'secret' });
      loginReq.flush(mockTokens);

      const meReq = httpMock.expectOne(`${API}/auth/me`);
      meReq.flush(mockUser);

      expect(service.getAccessToken()).toBe('access-123');
      expect(localStorage.getItem('guepard_refresh_token')).toBe('refresh-456');
      expect(service.currentUser).toEqual(mockUser);
      expect(service.isAuthenticated()).toBeTrue();
    });
  });

  describe('refreshAccessToken()', () => {
    it('is single-flight: two concurrent callers share one HTTP request', () => {
      localStorage.setItem('guepard_refresh_token', 'refresh-456');

      let firstResult: any;
      let secondResult: any;
      service.refreshAccessToken().subscribe((t) => (firstResult = t));
      service.refreshAccessToken().subscribe((t) => (secondResult = t));

      // Solo debe existir UNA request de refresh en vuelo, no dos.
      const req = httpMock.expectOne(`${API}/auth/refresh`);
      req.flush(mockTokens);

      expect(firstResult).toEqual(mockTokens);
      expect(secondResult).toEqual(mockTokens);
      expect(service.getAccessToken()).toBe('access-123');
    });

    it('errors immediately when there is no refresh token stored', (done) => {
      service.refreshAccessToken().subscribe({
        error: (err) => {
          expect(err).toBeTruthy();
          done();
        },
      });
    });
  });

  describe('logout()', () => {
    it('clears in-memory token, localStorage, current user, and redirects to /login', () => {
      localStorage.setItem('guepard_refresh_token', 'refresh-456');
      (service as any).accessToken = 'access-123';
      (service as any).currentUserSubject.next(mockUser);
      const navigateSpy = spyOn(router, 'navigate');

      service.logout();

      const logoutReq = httpMock.expectOne(`${API}/auth/logout`);
      logoutReq.flush(null);

      expect(service.getAccessToken()).toBeNull();
      expect(localStorage.getItem('guepard_refresh_token')).toBeNull();
      expect(service.currentUser).toBeNull();
      expect(navigateSpy).toHaveBeenCalledWith(['/login']);
    });
  });

  describe('restoreSession()', () => {
    it('resolves to null without any HTTP call when there is no refresh token', (done) => {
      service.restoreSession().subscribe((user) => {
        expect(user).toBeNull();
        done();
      });
    });

    it('clears session and resolves to null when the stored refresh token is rejected', (done) => {
      localStorage.setItem('guepard_refresh_token', 'stale-token');

      service.restoreSession().subscribe((user) => {
        expect(user).toBeNull();
        expect(localStorage.getItem('guepard_refresh_token')).toBeNull();
        done();
      });

      const req = httpMock.expectOne(`${API}/auth/refresh`);
      req.flush({ detail: 'invalid refresh token' }, { status: 401, statusText: 'Unauthorized' });
    });
  });
});
