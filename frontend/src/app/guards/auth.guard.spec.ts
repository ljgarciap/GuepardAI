import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, RouterStateSnapshot, provideRouter } from '@angular/router';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { authGuard } from './auth.guard';
import { AuthService } from '../services/auth.service';

describe('authGuard', () => {
  let authService: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [AuthService, provideRouter([])],
    });
    authService = TestBed.inject(AuthService);
  });

  function runGuard(url: string) {
    const route = {} as ActivatedRouteSnapshot;
    const state = { url } as RouterStateSnapshot;
    return TestBed.runInInjectionContext(() => authGuard(route, state));
  }

  it('allows navigation when the user is authenticated', () => {
    (authService as any).accessToken = 'token-abc';

    const result = runGuard('/brands');

    expect(result).toBeTrue();
  });

  it('redirects to /login with a returnUrl when there is no session', () => {
    const result: any = runGuard('/brands');

    expect(result).not.toBeTrue();
    expect(result.toString()).toContain('/login');
    expect(result.toString()).toContain('returnUrl');
  });
});
