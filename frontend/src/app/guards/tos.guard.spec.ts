import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, RouterStateSnapshot, provideRouter } from '@angular/router';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { firstValueFrom } from 'rxjs';
import { tosGuard } from './tos.guard';
import { TosService } from '../services/tos.service';

describe('tosGuard', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [TosService, provideRouter([])],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function runGuard(url: string) {
    const route = {} as ActivatedRouteSnapshot;
    const state = { url } as RouterStateSnapshot;
    return TestBed.runInInjectionContext(() => tosGuard(route, state));
  }

  it('allows navigation when the ToS is accepted', async () => {
    const resultPromise = firstValueFrom(runGuard('/brands') as any);

    httpMock.expectOne('/api/tos/status').flush({
      accepted: true, current_version: '1.1', accepted_version: '1.1', accepted_at: null, rejected_at: null,
    });

    expect(await resultPromise).toBeTrue();
  });

  it('redirects to /tos with a returnUrl when not accepted', async () => {
    const resultPromise = firstValueFrom(runGuard('/brands') as any);

    httpMock.expectOne('/api/tos/status').flush({
      accepted: false, current_version: '1.1', accepted_version: null, accepted_at: null, rejected_at: null,
    });

    const result: any = await resultPromise;
    expect(result).not.toBeTrue();
    expect(result.toString()).toContain('/tos');
    expect(result.toString()).toContain('returnUrl');
  });

  it('redirects to /tos when the status request fails', async () => {
    const resultPromise = firstValueFrom(runGuard('/brands') as any);

    httpMock.expectOne('/api/tos/status').flush('error', { status: 500, statusText: 'Server Error' });

    const result: any = await resultPromise;
    expect(result).not.toBeTrue();
    expect(result.toString()).toContain('/tos');
  });
});
