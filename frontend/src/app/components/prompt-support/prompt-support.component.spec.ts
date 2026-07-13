/**
 * prompt-support.component.spec.ts — facilidad de prompts compartida entre
 * Synthesis Studio y Template Merge (docs/designs/biblioteca-prompts-favoritos.md).
 */
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { PromptSupportComponent } from './prompt-support.component';
import { BrandService } from '../../services/brand.service';
import { PromptFavoritesService } from '../../services/prompt-favorites.service';
import { ConfirmDialogService } from '../../services/confirm-dialog.service';

describe('PromptSupportComponent', () => {
  let fixture: ComponentFixture<PromptSupportComponent>;
  let component: PromptSupportComponent;
  let brandSpy: jasmine.SpyObj<BrandService>;
  let favoritesSpy: jasmine.SpyObj<PromptFavoritesService>;
  let confirmSpy: jasmine.SpyObj<ConfirmDialogService>;

  beforeEach(async () => {
    brandSpy = jasmine.createSpyObj('BrandService', [
      'getLibraryPortfolios', 'getPortfolioDetail', 'getPromptIntents',
      'getTemplateMergeHistory', 'getTemplateMergeJobDetail',
    ]);
    favoritesSpy = jasmine.createSpyObj('PromptFavoritesService', ['listFavorites', 'createFavorite']);
    confirmSpy = jasmine.createSpyObj('ConfirmDialogService', ['confirm']);
    confirmSpy.confirm.and.returnValue(of(true));

    await TestBed.configureTestingModule({
      imports: [PromptSupportComponent],
      providers: [
        { provide: BrandService, useValue: brandSpy },
        { provide: PromptFavoritesService, useValue: favoritesSpy },
        { provide: ConfirmDialogService, useValue: confirmSpy },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(PromptSupportComponent);
    component = fixture.componentInstance;
  });

  describe('openReuseModal() per mode', () => {
    it('synthesis mode loads GenerationJob portfolios filtered by has_prompt', () => {
      component.mode = 'synthesis';
      brandSpy.getLibraryPortfolios.and.returnValue(of({
        items: [
          { id: 1, filename: 'a.pptx', display_name: 'a', created_at: '', brand_id: null, rating_average: null, rating_count: 0, my_rating: null, has_prompt: true },
          { id: 2, filename: 'b.pptx', display_name: 'b', created_at: '', brand_id: null, rating_average: null, rating_count: 0, my_rating: null, has_prompt: false },
        ],
        total: 2, page: 1, page_size: 50,
      }));

      component.openReuseModal();

      expect(component.showReuseModal).toBeTrue();
      expect(component.reusablePortfolios.length).toBe(1);
      expect(component.reusablePortfolios[0].id).toBe(1);
    });

    it('template-merge mode loads TemplateMergeJob history instead', () => {
      component.mode = 'template-merge';
      brandSpy.getTemplateMergeHistory.and.returnValue(of({
        items: [{ id: 5, filename: 'm.pptx', display_name: 'Merge A', created_at: '', brand_id: 1 }],
        total: 1, page: 1, page_size: 50,
      }));

      component.openReuseModal();

      expect(brandSpy.getTemplateMergeHistory).toHaveBeenCalled();
      expect(component.reusableMergeJobs.length).toBe(1);
      expect(component.reusableMergeJobs[0].id).toBe(5);
    });
  });

  describe('useAsBase() per mode', () => {
    it('synthesis mode pulls prompt + metadata from getPortfolioDetail and emits applyText', () => {
      component.mode = 'synthesis';
      component.currentText = '';
      brandSpy.getPortfolioDetail.and.returnValue(of({
        id: 1, filename: 'x.pptx', display_name: 'x', created_at: '', brand_id: 1,
        prompt: 'Reused prompt', prompt_metadata: { objective: 'reused' },
      }));
      const emitted: any[] = [];
      component.applyText.subscribe((e) => emitted.push(e));

      component.useAsBase(1);

      expect(emitted).toEqual([{ text: 'Reused prompt', metadata: { objective: 'reused' } }]);
      expect(component.showReuseModal).toBeFalse();
    });

    it('template-merge mode pulls prompt from getTemplateMergeJobDetail with null metadata', () => {
      component.mode = 'template-merge';
      component.currentText = '';
      brandSpy.getTemplateMergeJobDetail.and.returnValue(of({ job_id: 5, display_name: 'Merge A', prompt: 'Merge prompt' }));
      const emitted: any[] = [];
      component.applyText.subscribe((e) => emitted.push(e));

      component.useAsBase(5);

      expect(emitted).toEqual([{ text: 'Merge prompt', metadata: null }]);
    });

    it('emits loadError when the detail request fails', () => {
      component.mode = 'synthesis';
      brandSpy.getPortfolioDetail.and.returnValue(throwError(() => new Error('404')));
      let error = '';
      component.loadError.subscribe((e) => (error = e));

      component.useAsBase(1);

      expect(error).toContain('Could not load');
    });
  });

  describe('confirm-before-overwrite (regression: must not apply on cancel)', () => {
    it('applies the text when there is nothing to overwrite (no confirm needed)', () => {
      component.currentText = '';
      brandSpy.getPortfolioDetail.and.returnValue(of({
        id: 1, filename: 'x.pptx', display_name: 'x', created_at: '', brand_id: 1,
        prompt: 'New', prompt_metadata: null,
      }));
      let applied = false;
      component.applyText.subscribe(() => (applied = true));

      component.useAsBase(1);

      expect(applied).toBeTrue();
      expect(confirmSpy.confirm).not.toHaveBeenCalled();
    });

    it('asks for confirmation when overwriting existing manual text, and skips apply on cancel', () => {
      component.currentText = 'my own text';
      confirmSpy.confirm.and.returnValue(of(false));
      brandSpy.getPortfolioDetail.and.returnValue(of({
        id: 1, filename: 'x.pptx', display_name: 'x', created_at: '', brand_id: 1,
        prompt: 'New', prompt_metadata: null,
      }));
      let applied = false;
      component.applyText.subscribe(() => (applied = true));

      component.useAsBase(1);

      expect(confirmSpy.confirm).toHaveBeenCalled();
      expect(applied).toBeFalse();
      expect(component.showReuseModal).toBeFalse(); // no llegó a abrirse en este test, sigue en su default
    });
  });

  describe('selectIntent() — slide_type only prefilled in synthesis mode', () => {
    const intent = {
      slug: 'sales_deck', label: 'Sales Deck', expected_tone: 'Engaging',
      expected_duration_label: '10-15 min', narrative_style: 'Customer-centric storytelling',
      visual_density: 'medium', preferred_layouts: ['cover_hero', 'case_study'],
    };

    it('synthesis mode prefills slide_type from preferred_layouts', () => {
      component.mode = 'synthesis';
      component.selectIntent(intent);
      expect(component.composerInitialValues?.slide_type).toBe('cover_hero');
    });

    it('template-merge mode leaves slide_type empty (no layout choice in that pipeline)', () => {
      component.mode = 'template-merge';
      component.selectIntent(intent);
      expect(component.composerInitialValues?.slide_type).toBe('');
    });
  });

  describe('useFavorite()', () => {
    it('applies the favorite prompt and metadata, closing the modal', () => {
      component.currentText = '';
      component.showFavoritesModal = true;
      let emitted: any;
      component.applyText.subscribe((e) => (emitted = e));

      component.useFavorite({
        id: 1, title: 'Fav', prompt_text: 'Fav prompt', prompt_metadata: { objective: 'fav' },
        source_job_id: null, owner_email: 'me@example.com', created_at: '', updated_at: '',
      });

      expect(emitted).toEqual({ text: 'Fav prompt', metadata: { objective: 'fav' } });
      expect(component.showFavoritesModal).toBeFalse();
    });
  });

  describe('save-as-favorite flow', () => {
    it('confirmSaveFavorite() sends currentText/currentMetadata, not the modal own state', () => {
      component.currentText = 'the current prompt';
      component.currentMetadata = { objective: 'X' };
      component.saveFavoriteTitle = 'My favorite';
      favoritesSpy.createFavorite.and.returnValue(of({
        id: 1, title: 'My favorite', prompt_text: 'the current prompt', prompt_metadata: { objective: 'X' },
        source_job_id: null, owner_email: 'me@example.com', created_at: '', updated_at: '',
      }));

      component.confirmSaveFavorite();

      expect(favoritesSpy.createFavorite).toHaveBeenCalledWith({
        title: 'My favorite', prompt_text: 'the current prompt', prompt_metadata: { objective: 'X' },
      });
      expect(component.showSaveFavoriteModal).toBeFalse();
    });

    it('does nothing when the title is blank', () => {
      component.saveFavoriteTitle = '   ';
      component.confirmSaveFavorite();
      expect(favoritesSpy.createFavorite).not.toHaveBeenCalled();
    });
  });
});
