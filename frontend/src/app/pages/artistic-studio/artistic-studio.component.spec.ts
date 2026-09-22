import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { of, throwError, Subject } from 'rxjs';
import { ArtisticStudioComponent } from './artistic-studio.component';
import { ArtisticV2Service } from '../../services/artistic-v2.service';

describe('ArtisticStudioComponent — Artistic Generation Engine v2 (Phase 4)', () => {
  let fixture: ComponentFixture<ArtisticStudioComponent>;
  let component: ArtisticStudioComponent;
  let serviceSpy: jasmine.SpyObj<ArtisticV2Service>;

  beforeEach(async () => {
    serviceSpy = jasmine.createSpyObj('ArtisticV2Service', [
      'getEligibleBrands', 'generate', 'generateV1', 'getGenerationStatus',
    ]);
    serviceSpy.getEligibleBrands.and.returnValue(of({ brands: [{ id: 1, name: 'Tesco' }, { id: 5, name: 'Embonor' }] }));

    await TestBed.configureTestingModule({
      imports: [ArtisticStudioComponent],
      providers: [{ provide: ArtisticV2Service, useValue: serviceSpy }],
    }).compileComponents();

    fixture = TestBed.createComponent(ArtisticStudioComponent);
    component = fixture.componentInstance;
  });

  it('loads eligible brands and preselects the first one', () => {
    fixture.detectChanges();
    expect(component.eligibleBrands.length).toBe(2);
    expect(component.selectedBrandId).toBe(1);
  });

  it('surfaces a load error without crashing when eligible-brands fails', () => {
    serviceSpy.getEligibleBrands.and.returnValue(throwError(() => new Error('network')));
    fixture.detectChanges();
    expect(component.loadError).toBeTruthy();
    expect(component.eligibleBrands.length).toBe(0);
  });

  it('canGenerate is false without a prompt', () => {
    fixture.detectChanges();
    component.prompt = '';
    expect(component.canGenerate).toBeFalse();
  });

  it('canGenerate is true with a brand and a prompt', () => {
    fixture.detectChanges();
    component.prompt = 'Growth strategy';
    expect(component.canGenerate).toBeTrue();
  });

  it('generateBoth() fires both v1 and v2 requests for the same brand/prompt', () => {
    serviceSpy.generateV1.and.returnValue(of({ job_id: 100, status: 'pending' }));
    serviceSpy.generate.and.returnValue(of({ job_id: 200, status: 'pending', engine_version: 'v2_artistic' }));
    serviceSpy.getGenerationStatus.and.returnValue(of({
      id: 100, status: 'processing', progress: 10, current_step: 'working', qa_forced: false, download_url: null,
    }));

    fixture.detectChanges();
    component.prompt = 'Growth strategy';
    component.generateBoth();

    expect(serviceSpy.generateV1).toHaveBeenCalledWith({ brand_id: 1, prompt: 'Growth strategy' });
    expect(serviceSpy.generate).toHaveBeenCalledWith({ brand_id: 1, prompt: 'Growth strategy' });
    expect(component.v1.jobId).toBe(100);
    expect(component.v2.jobId).toBe(200);
  });

  it('a v1 start failure surfaces an error on the v1 column only', () => {
    serviceSpy.generateV1.and.returnValue(throwError(() => ({ error: { detail: 'boom' } })));
    serviceSpy.generate.and.returnValue(of({ job_id: 200, status: 'pending', engine_version: 'v2_artistic' }));
    serviceSpy.getGenerationStatus.and.returnValue(of({
      id: 200, status: 'processing', progress: 0, current_step: '', qa_forced: false, download_url: null,
    }));

    fixture.detectChanges();
    component.prompt = 'Growth strategy';
    component.generateBoth();

    expect(component.v1.error).toBe('boom');
    expect(component.v1.isRunning).toBeFalse();
    expect(component.v2.jobId).toBe(200);
  });

  it('reset() clears both columns and the prompt', () => {
    fixture.detectChanges();
    component.prompt = 'something';
    component.v1 = { jobId: 1, status: null, isRunning: false, error: null };
    component.v2 = { jobId: 2, status: null, isRunning: false, error: null };

    component.reset();

    expect(component.prompt).toBe('');
    expect(component.v1.jobId).toBeNull();
    expect(component.v2.jobId).toBeNull();
  });

  it('downloadUrl() returns null until the job is complete', () => {
    fixture.detectChanges();
    expect(component.downloadUrl(component.v1)).toBeNull();
  });

  // --- DOM-level regression coverage for the real bug found live (Luis) ---
  // Every test above only asserted component STATE, never what actually
  // renders — that's exactly why this shipped without being caught: the grid
  // was gated on `v1.jobId || v2.jobId`, invisible for however long the POST
  // took, or forever on failure. hasStarted fixes it; these tests pin the
  // DOM, not just the state, so a future regression here fails loudly.

  it('DOM: shows the comparison grid the instant generation starts, before any jobId exists', () => {
    // A POST that never resolves within this test — isRunning is true,
    // jobId is still null. The grid must already be visible.
    serviceSpy.generateV1.and.returnValue(new Subject());
    serviceSpy.generate.and.returnValue(new Subject());

    fixture.detectChanges();
    component.prompt = 'Growth strategy';
    component.generateBoth();
    fixture.detectChanges();

    expect(component.v1.jobId).toBeNull();
    const grid = fixture.nativeElement.querySelector('.comparison-grid');
    expect(grid).withContext('comparison grid must render while isRunning is true, even with no jobId yet').not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Starting...');
  });

  it('DOM: shows the v1 error message even though v1 never got a jobId', () => {
    serviceSpy.generateV1.and.returnValue(throwError(() => ({ error: { detail: 'boom' } })));
    serviceSpy.generate.and.returnValue(of({ job_id: 200, status: 'pending', engine_version: 'v2_artistic' }));
    serviceSpy.getGenerationStatus.and.returnValue(of({
      id: 200, status: 'processing', progress: 0, current_step: '', qa_forced: false, download_url: null,
    }));

    fixture.detectChanges();
    component.prompt = 'Growth strategy';
    component.generateBoth();
    fixture.detectChanges();

    expect(component.v1.jobId).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('boom');
  });

  it('DOM: shows the download link once a column completes', fakeAsync(() => {
    serviceSpy.generateV1.and.returnValue(of({ job_id: 100, status: 'pending' }));
    serviceSpy.generate.and.returnValue(new Subject());
    serviceSpy.getGenerationStatus.and.returnValue(of({
      id: 100, status: 'completed', progress: 100, current_step: 'Done', qa_forced: false,
      download_url: '/api/generation/download/100',
    }));

    fixture.detectChanges();
    component.prompt = 'Growth strategy';
    component.generateBoth();
    tick(2000); // pollColumn() polls on a 2s interval() — the first tick fires the first poll
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('.success-box a.btn-primary');
    expect(link).withContext('download link must render once status is completed').not.toBeNull();
  }));

  it('hasStarted is false before any generation and true as soon as isRunning flips on', () => {
    fixture.detectChanges();
    expect(component.hasStarted).toBeFalse();

    component.v1.isRunning = true;
    expect(component.hasStarted).toBeTrue();
  });
});
