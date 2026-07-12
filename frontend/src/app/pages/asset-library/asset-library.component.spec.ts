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
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { of, throwError } from 'rxjs';
import { AssetLibraryComponent } from './asset-library.component';
import { BrandService, PortfolioItem, PortfolioPage } from '../../services/brand.service';
import { CollaborationService } from '../../services/collaboration.service';
import { PromptFavoritesService, PromptFavorite } from '../../services/prompt-favorites.service';
import { ConfirmDialogService } from '../../services/confirm-dialog.service';
import { AuthService } from '../../services/auth.service';

describe('AssetLibraryComponent — Portfolio management', () => {
  let fixture: ComponentFixture<AssetLibraryComponent>;
  let component: AssetLibraryComponent;
  let brandServiceSpy: jasmine.SpyObj<BrandService>;
  let collabSpy: jasmine.SpyObj<CollaborationService>;

  const makeItem = (id: number, name: string): PortfolioItem => ({
    id,
    filename: `Presentation_${id}.pptx`,
    display_name: name,
    created_at: '2026-06-11T10:00:00',
    brand_id: null,
    rating: null,
    comment: null,
    has_prompt: true,
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

    collabSpy = jasmine.createSpyObj('CollaborationService', [
      'getReviews', 'getCollaborators', 'getUserDirectory', 'upsertReview', 'deleteOwnReview',
      'addCollaborator', 'removeCollaborator',
    ]);
    collabSpy.getReviews.and.returnValue(of({ reviews: [], rating_average: null, rating_count: 0 }));
    collabSpy.getCollaborators.and.returnValue(of([]));
    collabSpy.getUserDirectory.and.returnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [AssetLibraryComponent, HttpClientTestingModule],
      providers: [
        { provide: BrandService, useValue: brandServiceSpy },
        { provide: CollaborationService, useValue: collabSpy },
        { provide: AuthService, useValue: { currentUser: { id: 100, role: 'cliente' } } },
      ],
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

describe('AssetLibraryComponent — Presentation detail: reviews + collaborators', () => {
  let fixture: ComponentFixture<AssetLibraryComponent>;
  let component: AssetLibraryComponent;
  let collabSpy: jasmine.SpyObj<CollaborationService>;

  const makeItem = (id: number, name: string): PortfolioItem => ({
    id, filename: `Presentation_${id}.pptx`, display_name: name, created_at: '2026-06-11T10:00:00',
    brand_id: null, rating: null, comment: null, has_prompt: true,
  });

  beforeEach(async () => {
    const brandServiceSpy = jasmine.createSpyObj('BrandService', [
      'getBrands', 'getLibraryImages', 'getLibraryBlueprints', 'getLibraryKnowledge', 'getLibraryPortfolios',
    ]);
    brandServiceSpy.getBrands.and.returnValue(of([]));
    brandServiceSpy.getLibraryImages.and.returnValue(of([]));
    brandServiceSpy.getLibraryBlueprints.and.returnValue(of([]));
    brandServiceSpy.getLibraryKnowledge.and.returnValue(of([]));
    brandServiceSpy.getLibraryPortfolios.and.returnValue(of({ items: [], total: 0, page: 1, page_size: 12 }));

    collabSpy = jasmine.createSpyObj('CollaborationService', [
      'getReviews', 'getCollaborators', 'getUserDirectory', 'upsertReview', 'deleteOwnReview',
      'addCollaborator', 'removeCollaborator',
    ]);
    collabSpy.getReviews.and.returnValue(of({ reviews: [], rating_average: null, rating_count: 0 }));
    collabSpy.getCollaborators.and.returnValue(of([]));
    collabSpy.getUserDirectory.and.returnValue(of([
      { id: 100, email: 'me@example.com' },
      { id: 200, email: 'teammate@example.com' },
      { id: 300, email: 'already.collab@example.com' },
    ]));

    await TestBed.configureTestingModule({
      imports: [AssetLibraryComponent, HttpClientTestingModule],
      providers: [
        { provide: BrandService, useValue: brandServiceSpy },
        { provide: CollaborationService, useValue: collabSpy },
        { provide: AuthService, useValue: { currentUser: { id: 100, role: 'cliente' } } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AssetLibraryComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('openDetailModal() loads reviews, collaborators and the user directory', () => {
    const target = makeItem(5, 'Deck A');
    component.openDetailModal(target);

    expect(component.showDetailModal).toBeTrue();
    expect(component.detailJob).toBe(target);
    expect(collabSpy.getReviews).toHaveBeenCalledWith(5);
    expect(collabSpy.getCollaborators).toHaveBeenCalledWith(5);
    expect(collabSpy.getUserDirectory).toHaveBeenCalled();
  });

  it('prefills the rating/comment form with the current user\'s own existing review', () => {
    collabSpy.getReviews.and.returnValue(of({
      reviews: [
        { id: 1, job_id: 5, user_id: 100, user_email: 'me@example.com', rating: 4, comment: 'nice', created_at: '', updated_at: '', moderation_status: 'visible' },
      ],
      rating_average: 4, rating_count: 1,
    }));

    component.openDetailModal(makeItem(5, 'Deck A'));

    expect(component.myReviewRating).toBe(4);
    expect(component.myReviewComment).toBe('nice');
  });

  it('availableCollaboratorCandidates excludes the current user and existing collaborators', () => {
    collabSpy.getCollaborators.and.returnValue(of([
      { user_id: 300, email: 'already.collab@example.com', added_at: '' },
    ]));

    component.openDetailModal(makeItem(5, 'Deck A'));

    const emails = component.availableCollaboratorCandidates.map(c => c.email);
    expect(emails).toEqual(['teammate@example.com']);
  });

  it('closeDetailModal() resets the review form state', () => {
    component.myReviewRating = 5;
    component.myReviewComment = 'great';
    component.detailJob = makeItem(5, 'Deck A');
    component.showDetailModal = true;

    component.closeDetailModal();

    expect(component.showDetailModal).toBeFalse();
    expect(component.detailJob).toBeNull();
    expect(component.myReviewRating).toBe(0);
    expect(component.myReviewComment).toBe('');
  });

  describe('submitMyReview()', () => {
    it('does nothing when no rating is selected', () => {
      component.openDetailModal(makeItem(5, 'Deck A'));
      component.myReviewRating = 0;

      component.submitMyReview();

      expect(collabSpy.upsertReview).not.toHaveBeenCalled();
    });

    it('upserts the review and reloads the list on success', () => {
      component.openDetailModal(makeItem(5, 'Deck A'));
      collabSpy.upsertReview.and.returnValue(of({
        id: 1, job_id: 5, user_id: 100, user_email: 'me@example.com', rating: 5, comment: 'great',
        created_at: '', updated_at: '', moderation_status: 'visible',
      }));
      collabSpy.getReviews.calls.reset();
      component.myReviewRating = 5;
      component.myReviewComment = 'great';

      component.submitMyReview();

      expect(collabSpy.upsertReview).toHaveBeenCalledWith(5, 5, 'great');
      expect(collabSpy.getReviews).toHaveBeenCalledWith(5);
    });

    it('surfaces the backend error message (e.g. 6-month window closed)', () => {
      component.openDetailModal(makeItem(5, 'Deck A'));
      collabSpy.upsertReview.and.returnValue(throwError(() => ({ error: { detail: 'Review window closed (6 months after job creation)' } })));
      component.myReviewRating = 3;

      component.submitMyReview();

      expect(component.detailError).toBe('Review window closed (6 months after job creation)');
    });
  });

  describe('deleteMyReview()', () => {
    it('clears the local form and reloads on success', () => {
      component.openDetailModal(makeItem(5, 'Deck A'));
      collabSpy.deleteOwnReview.and.returnValue(of({ status: 'deleted' }));
      collabSpy.getReviews.calls.reset();
      component.myReviewRating = 4;
      component.myReviewComment = 'x';

      component.deleteMyReview();

      expect(collabSpy.deleteOwnReview).toHaveBeenCalledWith(5);
      expect(component.myReviewRating).toBe(0);
      expect(component.myReviewComment).toBe('');
      expect(collabSpy.getReviews).toHaveBeenCalledWith(5);
    });
  });

  describe('addCollaborator() / removeCollaborator()', () => {
    it('does nothing without a selected candidate', () => {
      component.openDetailModal(makeItem(5, 'Deck A'));
      component.selectedCollaboratorUserId = null;

      component.addCollaborator();

      expect(collabSpy.addCollaborator).not.toHaveBeenCalled();
    });

    it('adds the selected candidate and reloads the collaborator list', () => {
      component.openDetailModal(makeItem(5, 'Deck A'));
      collabSpy.addCollaborator.and.returnValue(of({ user_id: 200, added_at: '' }));
      collabSpy.getCollaborators.calls.reset();
      component.selectedCollaboratorUserId = 200;

      component.addCollaborator();

      expect(collabSpy.addCollaborator).toHaveBeenCalledWith(5, 200);
      expect(component.selectedCollaboratorUserId).toBeNull();
      expect(collabSpy.getCollaborators).toHaveBeenCalledWith(5);
    });

    it('surfaces a 403 error message (e.g. non-owner, non-admin)', () => {
      component.openDetailModal(makeItem(5, 'Deck A'));
      collabSpy.addCollaborator.and.returnValue(throwError(() => ({ error: { detail: 'Only the job owner or a tenant admin can manage collaborators' } })));
      component.selectedCollaboratorUserId = 200;

      component.addCollaborator();

      expect(component.collaboratorError).toBe('Only the job owner or a tenant admin can manage collaborators');
    });

    it('removes a collaborator and reloads the list', () => {
      component.openDetailModal(makeItem(5, 'Deck A'));
      collabSpy.removeCollaborator.and.returnValue(of({ status: 'removed' }));
      collabSpy.getCollaborators.calls.reset();

      component.removeCollaborator(300);

      expect(collabSpy.removeCollaborator).toHaveBeenCalledWith(5, 300);
      expect(collabSpy.getCollaborators).toHaveBeenCalledWith(5);
    });
  });
});

describe('AssetLibraryComponent — Prompt Favorites tab (biblioteca-prompts-favoritos)', () => {
  let fixture: ComponentFixture<AssetLibraryComponent>;
  let component: AssetLibraryComponent;
  let favoritesSpy: jasmine.SpyObj<PromptFavoritesService>;
  let confirmSpy: jasmine.SpyObj<ConfirmDialogService>;

  const makeFavorite = (id: number, title: string, ownerEmail = 'me@example.com'): PromptFavorite => ({
    id, title, prompt_text: `Prompt for ${title}`, prompt_metadata: null,
    source_job_id: null, owner_email: ownerEmail, created_at: '2026-07-12T10:00:00', updated_at: '2026-07-12T10:00:00',
  });

  beforeEach(async () => {
    const brandServiceSpy = jasmine.createSpyObj('BrandService', [
      'getBrands', 'getLibraryImages', 'getLibraryBlueprints', 'getLibraryKnowledge', 'getLibraryPortfolios',
    ]);
    brandServiceSpy.getBrands.and.returnValue(of([]));
    brandServiceSpy.getLibraryImages.and.returnValue(of([]));
    brandServiceSpy.getLibraryBlueprints.and.returnValue(of([]));
    brandServiceSpy.getLibraryKnowledge.and.returnValue(of([]));
    brandServiceSpy.getLibraryPortfolios.and.returnValue(of({ items: [], total: 0, page: 1, page_size: 12 }));

    const collabSpy = jasmine.createSpyObj('CollaborationService', [
      'getReviews', 'getCollaborators', 'getUserDirectory',
    ]);
    collabSpy.getReviews.and.returnValue(of({ reviews: [], rating_average: null, rating_count: 0 }));
    collabSpy.getCollaborators.and.returnValue(of([]));
    collabSpy.getUserDirectory.and.returnValue(of([]));

    favoritesSpy = jasmine.createSpyObj('PromptFavoritesService', [
      'listFavorites', 'createFavorite', 'updateFavorite', 'deleteFavorite',
    ]);
    favoritesSpy.listFavorites.and.returnValue(of([makeFavorite(1, 'Q3 Deck')]));

    confirmSpy = jasmine.createSpyObj('ConfirmDialogService', ['confirm']);
    confirmSpy.confirm.and.returnValue(of(true));

    await TestBed.configureTestingModule({
      imports: [AssetLibraryComponent, HttpClientTestingModule],
      providers: [
        { provide: BrandService, useValue: brandServiceSpy },
        { provide: CollaborationService, useValue: collabSpy },
        { provide: PromptFavoritesService, useValue: favoritesSpy },
        { provide: ConfirmDialogService, useValue: confirmSpy },
        { provide: AuthService, useValue: { currentUser: { id: 100, role: 'cliente' } } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AssetLibraryComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('loads favorites when switching to the prompts tab', () => {
    component.setTab('prompts');

    expect(favoritesSpy.listFavorites).toHaveBeenCalled();
    expect(component.favorites.length).toBe(1);
    expect(component.favorites[0].title).toBe('Q3 Deck');
  });

  it('startEditFavorite() / cancelEditFavorite() toggle the inline editor state', () => {
    component.setTab('prompts');
    const fav = component.favorites[0];

    component.startEditFavorite(fav);
    expect(component.editingFavoriteId).toBe(fav.id);
    expect(component.editFavoriteTitle).toBe(fav.title);
    expect(component.editFavoritePromptText).toBe(fav.prompt_text);

    component.cancelEditFavorite();
    expect(component.editingFavoriteId).toBeNull();
  });

  it('confirmEditFavorite() updates the item in place and closes the editor', () => {
    component.setTab('prompts');
    const fav = component.favorites[0];
    component.startEditFavorite(fav);
    component.editFavoriteTitle = 'Renamed';
    component.editFavoritePromptText = 'New prompt text';
    favoritesSpy.updateFavorite.and.returnValue(of({ ...fav, title: 'Renamed', prompt_text: 'New prompt text' }));

    component.confirmEditFavorite();

    expect(favoritesSpy.updateFavorite).toHaveBeenCalledWith(fav.id, { title: 'Renamed', prompt_text: 'New prompt text' });
    expect(component.favorites[0].title).toBe('Renamed');
    expect(component.editingFavoriteId).toBeNull();
  });

  it('confirmEditFavorite() does nothing when the title is blank', () => {
    component.setTab('prompts');
    component.startEditFavorite(component.favorites[0]);
    component.editFavoriteTitle = '   ';

    component.confirmEditFavorite();

    expect(favoritesSpy.updateFavorite).not.toHaveBeenCalled();
  });

  it('deleteFavorite() asks for confirmation and removes the item from the list on success', () => {
    confirmSpy.confirm.and.returnValue(of(true));
    component.setTab('prompts');
    favoritesSpy.deleteFavorite.and.returnValue(of({ deleted: true, id: 1 }));

    component.deleteFavorite(component.favorites[0]);

    expect(confirmSpy.confirm).toHaveBeenCalled();
    expect(favoritesSpy.deleteFavorite).toHaveBeenCalledWith(1);
    expect(component.favorites.length).toBe(0);
  });

  it('deleteFavorite() does nothing when the user cancels the confirmation', () => {
    confirmSpy.confirm.and.returnValue(of(false));
    component.setTab('prompts');

    component.deleteFavorite(component.favorites[0]);

    expect(favoritesSpy.deleteFavorite).not.toHaveBeenCalled();
    expect(component.favorites.length).toBe(1);
  });
});
