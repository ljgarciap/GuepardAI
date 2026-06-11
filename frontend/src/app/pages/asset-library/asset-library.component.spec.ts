/**
 * asset-library.component.spec.ts — Lógica de Gestión de Portfolios.
 *
 * Cubre: carga paginada, debounce de búsqueda → reset a página 1, cambio de
 * fechas → reset, modal de borrado (confirmar/cancelar), retroceso de página
 * al borrar el último ítem, y renombrado inline.
 *
 * Spec: docs/specs/gestion-portfolios.md
 */
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { of } from 'rxjs';
import { AssetLibraryComponent } from './asset-library.component';
import { BrandService, PortfolioItem, PortfolioPage } from '../../services/brand.service';

describe('AssetLibraryComponent — Portfolio management', () => {
  let fixture: ComponentFixture<AssetLibraryComponent>;
  let component: AssetLibraryComponent;
  let brandServiceSpy: jasmine.SpyObj<BrandService>;

  const makeItem = (id: number, name: string): PortfolioItem => ({
    id,
    filename: `Presentation_${id}.pptx`,
    display_name: name,
    created_at: '2026-06-11T10:00:00',
    brand_id: null,
    rating: null,
    comment: null,
  });

  const makePage = (items: PortfolioItem[], total: number, page = 1): PortfolioPage => ({
    items, total, page, page_size: 12,
  });

  beforeEach(async () => {
    brandServiceSpy = jasmine.createSpyObj('BrandService', [
      'getBrands', 'getLibraryImages', 'getLibraryBlueprints', 'getLibraryKnowledge',
      'getLibraryPortfolios', 'renamePortfolio', 'deletePortfolio', 'submitFeedback',
    ]);
    brandServiceSpy.getBrands.and.returnValue(of([]));
    brandServiceSpy.getLibraryImages.and.returnValue(of([]));
    brandServiceSpy.getLibraryBlueprints.and.returnValue(of([]));
    brandServiceSpy.getLibraryKnowledge.and.returnValue(of([]));
    brandServiceSpy.getLibraryPortfolios.and.returnValue(of(makePage([makeItem(1, 'Deck A')], 1)));

    await TestBed.configureTestingModule({
      imports: [AssetLibraryComponent],
      providers: [{ provide: BrandService, useValue: brandServiceSpy }],
    }).compileComponents();

    fixture = TestBed.createComponent(AssetLibraryComponent);
    component = fixture.componentInstance;
    fixture.detectChanges(); // ngOnInit (tab inicial = images)
  });

  it('should load portfolios with pagination params when switching to the tab', () => {
    component.setTab('portfolios');

    expect(brandServiceSpy.getLibraryPortfolios).toHaveBeenCalledWith(undefined, jasmine.objectContaining({
      page: 1,
      pageSize: 12,
    }));
    expect(component.portfolios.length).toBe(1);
    expect(component.portfolioTotal).toBe(1);
  });

  it('should debounce search and reset to page 1', fakeAsync(() => {
    component.setTab('portfolios');
    component.portfolioPage = 4;
    brandServiceSpy.getLibraryPortfolios.calls.reset();

    component.portfolioSearch = 'Tesco';
    component.onPortfolioSearchChange('Tesco');
    expect(brandServiceSpy.getLibraryPortfolios).not.toHaveBeenCalled(); // aún en debounce

    tick(300);
    expect(brandServiceSpy.getLibraryPortfolios).toHaveBeenCalledTimes(1);
    expect(component.portfolioPage).toBe(1);
    const opts = brandServiceSpy.getLibraryPortfolios.calls.mostRecent().args[1];
    expect(opts?.search).toBe('Tesco');
  }));

  it('should reset to page 1 when a date filter changes', () => {
    component.setTab('portfolios');
    component.portfolioPage = 3;
    brandServiceSpy.getLibraryPortfolios.calls.reset();

    component.portfolioDateFrom = '2026-06-01';
    component.onPortfolioDateChange();

    expect(component.portfolioPage).toBe(1);
    const opts = brandServiceSpy.getLibraryPortfolios.calls.mostRecent().args[1];
    expect(opts?.dateFrom).toBe('2026-06-01');
  });

  it('should compute total pages from total and page size', () => {
    component.portfolioTotal = 25;
    component.portfolioPageSize = 12;
    expect(component.portfolioTotalPages).toBe(3);

    component.portfolioTotal = 0;
    expect(component.portfolioTotalPages).toBe(1);
  });

  it('cancelling the delete modal must not call the service', () => {
    const target = makeItem(7, 'Deck to keep');
    component.askDeletePortfolio(target);
    expect(component.showDeleteModal).toBeTrue();
    expect(component.deleteTarget).toBe(target);

    component.cancelDeletePortfolio();

    expect(component.showDeleteModal).toBeFalse();
    expect(component.deleteTarget).toBeNull();
    expect(brandServiceSpy.deletePortfolio).not.toHaveBeenCalled();
  });

  it('confirming the delete modal calls DELETE and reloads the list', () => {
    component.setTab('portfolios');
    brandServiceSpy.deletePortfolio.and.returnValue(of({ deleted: true, id: 1 }));
    brandServiceSpy.getLibraryPortfolios.calls.reset();
    brandServiceSpy.getLibraryPortfolios.and.returnValue(of(makePage([], 0)));

    component.askDeletePortfolio(component.portfolios[0]);
    component.confirmDeletePortfolio();

    expect(brandServiceSpy.deletePortfolio).toHaveBeenCalledWith(1);
    expect(brandServiceSpy.getLibraryPortfolios).toHaveBeenCalled();
    expect(component.showDeleteModal).toBeFalse();
  });

  it('deleting the last item of a page > 1 steps back one page', () => {
    component.setTab('portfolios');
    component.portfolioPage = 2;
    component.portfolios = [makeItem(9, 'Last of page 2')];
    brandServiceSpy.deletePortfolio.and.returnValue(of({ deleted: true, id: 9 }));
    brandServiceSpy.getLibraryPortfolios.and.returnValue(of(makePage([makeItem(1, 'A')], 12, 1)));

    component.askDeletePortfolio(component.portfolios[0]);
    component.confirmDeletePortfolio();

    expect(component.portfolioPage).toBe(1);
  });

  it('confirming a rename updates the item in place', () => {
    component.setTab('portfolios');
    brandServiceSpy.renamePortfolio.and.returnValue(of({
      id: 1, display_name: 'Renamed Deck', filename: 'Presentation_1.pptx',
    }));

    component.startRename(component.portfolios[0]);
    expect(component.renamingJobId).toBe(1);
    component.renameValue = 'Renamed Deck';
    component.confirmRename();

    expect(brandServiceSpy.renamePortfolio).toHaveBeenCalledWith(1, 'Renamed Deck');
    expect(component.portfolios[0].display_name).toBe('Renamed Deck');
    expect(component.renamingJobId).toBeNull();
  });

  it('an empty rename must not call the service', () => {
    component.setTab('portfolios');
    component.startRename(component.portfolios[0]);
    component.renameValue = '   ';
    component.confirmRename();

    expect(brandServiceSpy.renamePortfolio).not.toHaveBeenCalled();
  });
});
