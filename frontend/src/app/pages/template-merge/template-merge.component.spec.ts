/**
 * template-merge.component.spec.ts — Histórico persistente de Template Merge.
 *
 * Cubre: carga paginada al activar la pestaña History, debounce de búsqueda →
 * reset a página 1, cambio de fechas → reset, modal de borrado
 * (confirmar/cancelar), retroceso de página al borrar el último ítem, y
 * renombrado inline.
 *
 * Spec: docs/specs/template-merge-job-history.md
 */
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { TemplateMergeComponent } from './template-merge.component';
import { BrandService, TemplateMergeHistoryItem, TemplateMergeHistoryPage } from '../../services/brand.service';

describe('TemplateMergeComponent — History tab', () => {
  let fixture: ComponentFixture<TemplateMergeComponent>;
  let component: TemplateMergeComponent;
  let httpMock: HttpTestingController;
  let brandServiceSpy: jasmine.SpyObj<BrandService>;

  const makeItem = (id: number, name: string): TemplateMergeHistoryItem => ({
    id,
    filename: `Merge_${id}.pptx`,
    display_name: name,
    created_at: '2026-07-07T10:00:00',
    brand_id: null,
  });

  const makePage = (items: TemplateMergeHistoryItem[], total: number, page = 1): TemplateMergeHistoryPage => ({
    items, total, page, page_size: 12,
  });

  beforeEach(async () => {
    brandServiceSpy = jasmine.createSpyObj('BrandService', [
      'getTemplateMergeHistory', 'renameTemplateMergeJob', 'deleteTemplateMergeJob', 'getBrands',
    ]);
    brandServiceSpy.getTemplateMergeHistory.and.returnValue(of(makePage([makeItem(1, 'Merge A')], 1)));
    brandServiceSpy.getBrands.and.returnValue(of([{ id: 1, name: 'Tesco' }, { id: 2, name: 'Acme' }]));

    await TestBed.configureTestingModule({
      imports: [TemplateMergeComponent, HttpClientTestingModule],
      providers: [{ provide: BrandService, useValue: brandServiceSpy }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(TemplateMergeComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges(); // ngOnInit -> loadTemplates() + loadKnowledgeSources() (HttpClient directo)

    // Las dos llamadas de ngOnInit no son parte de este feature; se drenan para
    // que httpMock.verify() no falle por peticiones pendientes.
    httpMock.match(() => true).forEach(req => req.flush([]));
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should load history with pagination params when switching to the history view', () => {
    component.setView('history');

    expect(brandServiceSpy.getTemplateMergeHistory).toHaveBeenCalledWith(undefined, jasmine.objectContaining({
      page: 1,
      pageSize: 12,
    }));
    expect(component.historyItems.length).toBe(1);
    expect(component.historyTotal).toBe(1);
  });

  it('should debounce search and reset to page 1', fakeAsync(() => {
    component.setView('history');
    component.historyPage = 4;
    brandServiceSpy.getTemplateMergeHistory.calls.reset();

    component.historySearch = 'Tesco';
    component.onHistorySearchChange('Tesco');
    expect(brandServiceSpy.getTemplateMergeHistory).not.toHaveBeenCalled(); // aún en debounce

    tick(300);
    expect(brandServiceSpy.getTemplateMergeHistory).toHaveBeenCalledTimes(1);
    expect(component.historyPage).toBe(1);
    const opts = brandServiceSpy.getTemplateMergeHistory.calls.mostRecent().args[1];
    expect(opts?.search).toBe('Tesco');
  }));

  it('should reset to page 1 when a date filter changes', () => {
    component.setView('history');
    component.historyPage = 3;
    brandServiceSpy.getTemplateMergeHistory.calls.reset();

    component.historyDateFrom = '2026-07-01';
    component.onHistoryDateChange();

    expect(component.historyPage).toBe(1);
    const opts = brandServiceSpy.getTemplateMergeHistory.calls.mostRecent().args[1];
    expect(opts?.dateFrom).toBe('2026-07-01');
  });

  it('should compute total pages from total and page size', () => {
    component.historyTotal = 25;
    component.historyPageSize = 12;
    expect(component.historyTotalPages).toBe(3);

    component.historyTotal = 0;
    expect(component.historyTotalPages).toBe(1);
  });

  it('cancelling the delete modal must not call the service', () => {
    const target = makeItem(7, 'Merge to keep');
    component.askDeleteHistoryItem(target);
    expect(component.showDeleteModal).toBeTrue();
    expect(component.deleteTarget).toBe(target);

    component.cancelDeleteHistoryItem();

    expect(component.showDeleteModal).toBeFalse();
    expect(component.deleteTarget).toBeNull();
    expect(brandServiceSpy.deleteTemplateMergeJob).not.toHaveBeenCalled();
  });

  it('confirming the delete modal calls DELETE and reloads the list', () => {
    component.setView('history');
    brandServiceSpy.deleteTemplateMergeJob.and.returnValue(of({ deleted: true, id: 1 }));
    brandServiceSpy.getTemplateMergeHistory.calls.reset();
    brandServiceSpy.getTemplateMergeHistory.and.returnValue(of(makePage([], 0)));

    component.askDeleteHistoryItem(component.historyItems[0]);
    component.confirmDeleteHistoryItem();

    expect(brandServiceSpy.deleteTemplateMergeJob).toHaveBeenCalledWith(1);
    expect(brandServiceSpy.getTemplateMergeHistory).toHaveBeenCalled();
    expect(component.showDeleteModal).toBeFalse();
  });

  it('deleting the last item of a page > 1 steps back one page', () => {
    component.setView('history');
    component.historyPage = 2;
    component.historyItems = [makeItem(9, 'Last of page 2')];
    brandServiceSpy.deleteTemplateMergeJob.and.returnValue(of({ deleted: true, id: 9 }));
    brandServiceSpy.getTemplateMergeHistory.and.returnValue(of(makePage([makeItem(1, 'A')], 12, 1)));

    component.askDeleteHistoryItem(component.historyItems[0]);
    component.confirmDeleteHistoryItem();

    expect(component.historyPage).toBe(1);
  });

  it('confirming a rename updates the item in place', () => {
    component.setView('history');
    brandServiceSpy.renameTemplateMergeJob.and.returnValue(of({
      id: 1, display_name: 'Renamed Merge', filename: 'Merge_1.pptx',
    }));

    component.startHistoryRename(component.historyItems[0]);
    expect(component.renamingHistoryId).toBe(1);
    component.renameValue = 'Renamed Merge';
    component.confirmHistoryRename();

    expect(brandServiceSpy.renameTemplateMergeJob).toHaveBeenCalledWith(1, 'Renamed Merge');
    expect(component.historyItems[0].display_name).toBe('Renamed Merge');
    expect(component.renamingHistoryId).toBeNull();
  });

  it('an empty rename must not call the service', () => {
    component.setView('history');
    component.startHistoryRename(component.historyItems[0]);
    component.renameValue = '   ';
    component.confirmHistoryRename();

    expect(brandServiceSpy.renameTemplateMergeJob).not.toHaveBeenCalled();
  });

  // ── Brand selection & submit() ─────────────────────────────────────────────

  describe('brand selection & submit()', () => {
    it('loads brands and does not auto-select when there is more than one', () => {
      expect(component.brands.length).toBe(2);
      expect(component.selectedBrandId).toBeNull();
    });

    it('canSubmit is false without a selected brand even if the rest of the form is filled', () => {
      component.selectedTemplateId = 1;
      component.selectedKnowledge = 'doc.pdf';
      component.prompt = 'Some prompt';

      expect(component.canSubmit).toBeFalse();
    });

    it('submit() includes brand_id in the POST payload', () => {
      component.selectedBrandId = 2;
      component.selectedTemplateId = 1;
      component.selectedKnowledge = 'doc.pdf';
      component.prompt = 'Some prompt';

      component.submit();

      const req = httpMock.expectOne(r => r.url.endsWith('/template-merge/jobs') && r.method === 'POST');
      expect(req.request.body.brand_id).toBe(2);
      req.flush({ job_id: 1, status: 'pending', message: 'ok' });
    });
  });

  // ── Merge report summary (v2) ──────────────────────────────────────────────

  describe('merge report summary getters', () => {
    const summary = {
      rewritten: 4, adapted: 2, preserved: 3, unfilled: 1, kept_original: 1, failed: 1,
    };

    it('exposes replaced and warning counts from the completed job summary', () => {
      component.activeJob = {
        job_id: 1, status: 'completed', progress: 100, current_step: 'Done.',
        error_detail: null, output_url: 'x', display_name: null,
        merge_summary: summary,
      };

      expect(component.mergeSummary).toEqual(summary);
      expect(component.mergeReplacedCount).toBe(6);   // rewritten + adapted
      expect(component.mergeWarningCount).toBe(2);    // unfilled + failed
    });

    it('returns null summary and zero counts for pre-v2 jobs (no merge_summary)', () => {
      component.activeJob = {
        job_id: 1, status: 'completed', progress: 100, current_step: 'Done.',
        error_detail: null, output_url: 'x', display_name: null,
      };

      expect(component.mergeSummary).toBeNull();
      expect(component.mergeWarningCount).toBe(0);
      expect(component.mergeReplacedCount).toBe(0);
    });

    it('exposes visual QA findings flattened with slide numbers (phase 4)', () => {
      component.activeJob = {
        job_id: 1, status: 'completed', progress: 100, current_step: 'Done.',
        error_detail: null, output_url: 'x', display_name: null,
        merge_report: {
          visual_qa: {
            status: 'ok', total_findings: 2, slides_reviewed: 3,
            slides: [
              { slide: 1, findings: [{ type: 'overflow', severity: 'high', detail: 'Title cut' }] },
              { slide: 3, findings: [{ type: 'contrast', severity: 'low', detail: 'Footer faint' }] },
            ],
          },
        },
      };

      expect(component.visualQaFindingCount).toBe(2);
      expect(component.visualQaFindings).toEqual([
        { slide: 1, type: 'overflow', severity: 'high', detail: 'Title cut' },
        { slide: 3, type: 'contrast', severity: 'low', detail: 'Footer faint' },
      ]);
    });

    it('hides visual QA when the pass did not run cleanly (unavailable/failed/absent)', () => {
      component.activeJob = {
        job_id: 1, status: 'completed', progress: 100, current_step: 'Done.',
        error_detail: null, output_url: 'x', display_name: null,
        merge_report: { visual_qa: { status: 'failed', detail: 'boom' } },
      };

      expect(component.visualQa).toBeNull();
      expect(component.visualQaFindingCount).toBe(0);
      expect(component.visualQaFindings).toEqual([]);
    });
  });
});

describe('TemplateMergeComponent — Knowledge sources (regression: stale brand_id=-1 sentinel)', () => {
  let fixture: ComponentFixture<TemplateMergeComponent>;
  let component: TemplateMergeComponent;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    const brandServiceSpy = jasmine.createSpyObj('BrandService', [
      'getTemplateMergeHistory', 'renameTemplateMergeJob', 'deleteTemplateMergeJob', 'getBrands',
    ]);
    brandServiceSpy.getTemplateMergeHistory.and.returnValue(of({ items: [], total: 0, page: 1, page_size: 12 }));
    brandServiceSpy.getBrands.and.returnValue(of([{ id: 1, name: 'Tesco' }, { id: 2, name: 'Acme' }]));

    await TestBed.configureTestingModule({
      imports: [TemplateMergeComponent, HttpClientTestingModule],
      providers: [{ provide: BrandService, useValue: brandServiceSpy }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(TemplateMergeComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges(); // ngOnInit -> loadTemplates() + loadKnowledgeSources()

    // loadTemplates() no es parte de esta regresión — se drena sin inspeccionar.
    httpMock.match(r => r.url.endsWith('/template-merge/templates')).forEach(req => req.flush([]));
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('requests /available-knowledge WITHOUT brand_id on initial load (no selected brand yet)', () => {
    const req = httpMock.expectOne(r => r.url.includes('/available-knowledge'));
    expect(req.request.urlWithParams).not.toContain('brand_id=-1');
    expect(req.request.urlWithParams).not.toContain('brand_id');
    req.flush({ sources: [] });
  });

  it('onBrandChange() re-fetches /available-knowledge scoped to the selected brand', () => {
    httpMock.expectOne(r => r.url.includes('/available-knowledge')).flush({ sources: [] });

    component.selectedBrandId = 2;
    component.onBrandChange();

    const req = httpMock.expectOne(r => r.url.includes('/available-knowledge'));
    expect(req.request.urlWithParams).toContain('brand_id=2');
    req.flush({ sources: ['doc.pdf'] });

    expect(component.availableKnowledge).toEqual(['doc.pdf']);
  });
});

describe('TemplateMergeComponent — Knowledge sources (regression: single-brand auto-select never rescoped the list)', () => {
  // Bug 2026-07-13: con un único brand, loadBrands() lo auto-selecciona
  // programáticamente y eso NO dispara (ngModelChange) — el dropdown quedaba
  // solo con knowledge público (vacío para un admin con knowledge privado).
  let fixture: ComponentFixture<TemplateMergeComponent>;
  let component: TemplateMergeComponent;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    const brandServiceSpy = jasmine.createSpyObj('BrandService', [
      'getTemplateMergeHistory', 'renameTemplateMergeJob', 'deleteTemplateMergeJob', 'getBrands',
    ]);
    brandServiceSpy.getTemplateMergeHistory.and.returnValue(of({ items: [], total: 0, page: 1, page_size: 12 }));
    brandServiceSpy.getBrands.and.returnValue(of([{ id: 1, name: 'Tesco' }]));

    await TestBed.configureTestingModule({
      imports: [TemplateMergeComponent, HttpClientTestingModule],
      providers: [{ provide: BrandService, useValue: brandServiceSpy }, provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(TemplateMergeComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();

    httpMock.match(r => r.url.endsWith('/template-merge/templates')).forEach(req => req.flush([]));
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('auto-selecting the only brand re-fetches /available-knowledge scoped to it', () => {
    expect(component.selectedBrandId).toBe(1);

    const requests = httpMock.match(r => r.url.includes('/available-knowledge'));
    expect(requests.some(r => r.request.urlWithParams.includes('brand_id=1'))).toBeTrue();
    requests.forEach(r => r.flush({ sources: ['Tesco Annual Report.pdf'] }));

    expect(component.availableKnowledge).toEqual(['Tesco Annual Report.pdf']);
  });
});
