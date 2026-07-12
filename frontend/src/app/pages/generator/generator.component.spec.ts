import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { GeneratorComponent } from './generator.component';
import { BrandService } from '../../services/brand.service';
import { PromptFavoritesService } from '../../services/prompt-favorites.service';
import { AuthService } from '../../services/auth.service';

describe('GeneratorComponent — prompt support (soporte-indicaciones)', () => {
  let fixture: ComponentFixture<GeneratorComponent>;
  let component: GeneratorComponent;
  let brandSpy: jasmine.SpyObj<BrandService>;
  let favoritesSpy: jasmine.SpyObj<PromptFavoritesService>;

  beforeEach(async () => {
    brandSpy = jasmine.createSpyObj('BrandService', [
      'getBrands', 'getAvailableStyles', 'getAvailableKnowledge', 'getAvailableDialects',
      'getLibraryPortfolios', 'getPortfolioDetail', 'getPromptIntents', 'generatePresentation',
    ]);
    brandSpy.getBrands.and.returnValue(of([]));
    brandSpy.getAvailableStyles.and.returnValue(of({ styles: [] }));
    brandSpy.getAvailableKnowledge.and.returnValue(of({ sources: [] }));
    brandSpy.getAvailableDialects.and.returnValue(of([]));

    favoritesSpy = jasmine.createSpyObj('PromptFavoritesService', [
      'listFavorites', 'createFavorite', 'updateFavorite', 'deleteFavorite',
    ]);

    await TestBed.configureTestingModule({
      imports: [GeneratorComponent],
      providers: [
        { provide: BrandService, useValue: brandSpy },
        { provide: PromptFavoritesService, useValue: favoritesSpy },
        { provide: AuthService, useValue: { currentUser: { role: 'cliente' } } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(GeneratorComponent);
    component = fixture.componentInstance;
    fixture.detectChanges(); // ngOnInit
  });

  describe('applyPromptText() — confirm-cancel state consistency', () => {
    it('replaces the prompt directly when the textarea is empty (no confirm needed)', () => {
      component.prompt = '';
      const result = (component as any).applyPromptText('New prompt text');
      expect(result).toBeTrue();
      expect(component.prompt).toBe('New prompt text');
    });

    it('replaces the prompt when the user confirms the overwrite', () => {
      spyOn(window, 'confirm').and.returnValue(true);
      component.prompt = 'existing manual text';
      const result = (component as any).applyPromptText('New prompt text');
      expect(result).toBeTrue();
      expect(component.prompt).toBe('New prompt text');
    });

    it('does NOT replace the prompt and returns false when the user cancels', () => {
      spyOn(window, 'confirm').and.returnValue(false);
      component.prompt = 'existing manual text';
      const result = (component as any).applyPromptText('New prompt text');
      expect(result).toBeFalse();
      expect(component.prompt).toBe('existing manual text');
    });
  });

  describe('useAsBase() — regression: must not overwrite promptMetadata on cancel', () => {
    it('applies prompt and metadata, and closes the modal on success', () => {
      component.prompt = '';
      component.showReuseModal = true;
      brandSpy.getPortfolioDetail.and.returnValue(of({
        id: 1, filename: 'x.pptx', display_name: 'x', created_at: '2026-01-01', brand_id: 1,
        prompt: 'Reused prompt', prompt_metadata: { objective: 'reused' },
      }));

      component.useAsBase(1);

      expect(component.prompt).toBe('Reused prompt');
      expect(component.promptMetadata).toEqual({ objective: 'reused' });
      expect(component.showReuseModal).toBeFalse();
    });

    it('leaves promptMetadata untouched and modal open when the user cancels the overwrite', () => {
      component.prompt = 'my own text';
      component.promptMetadata = null;
      component.showReuseModal = true;
      spyOn(window, 'confirm').and.returnValue(false);
      brandSpy.getPortfolioDetail.and.returnValue(of({
        id: 1, filename: 'x.pptx', display_name: 'x', created_at: '2026-01-01', brand_id: 1,
        prompt: 'Reused prompt', prompt_metadata: { objective: 'reused' },
      }));

      component.useAsBase(1);

      expect(component.prompt).toBe('my own text');
      expect(component.promptMetadata).toBeNull();
      expect(component.showReuseModal).toBeTrue();
    });

    it('sets an error message when the detail request fails', () => {
      brandSpy.getPortfolioDetail.and.returnValue(throwError(() => new Error('404')));
      component.useAsBase(1);
      expect(component.errorMessage).toContain('Could not load');
    });
  });

  describe('onComposerInsert() — regression: must not overwrite promptMetadata on cancel', () => {
    it('applies the assembled text and metadata, and closes the modal on success', () => {
      component.prompt = '';
      component.showComposerModal = true;

      component.onComposerInsert({ text: 'Objective: X.', metadata: { objective: 'X' } });

      expect(component.prompt).toBe('Objective: X.');
      expect(component.promptMetadata).toEqual({ objective: 'X' });
      expect(component.showComposerModal).toBeFalse();
    });

    it('leaves promptMetadata untouched and modal open when the user cancels the overwrite', () => {
      component.prompt = 'my own text';
      component.promptMetadata = null;
      component.showComposerModal = true;
      spyOn(window, 'confirm').and.returnValue(false);

      component.onComposerInsert({ text: 'Objective: X.', metadata: { objective: 'X' } });

      expect(component.prompt).toBe('my own text');
      expect(component.promptMetadata).toBeNull();
      expect(component.showComposerModal).toBeTrue();
    });
  });

  describe('openReuseModal()', () => {
    it('loads only portfolios that have a reusable prompt', () => {
      brandSpy.getLibraryPortfolios.and.returnValue(of({
        items: [
          { id: 1, filename: 'a.pptx', display_name: 'a', created_at: '', brand_id: null, rating: null, comment: null, has_prompt: true },
          { id: 2, filename: 'b.pptx', display_name: 'b', created_at: '', brand_id: null, rating: null, comment: null, has_prompt: false },
        ],
        total: 2, page: 1, page_size: 50,
      }));

      component.openReuseModal();

      expect(component.showReuseModal).toBeTrue();
      expect(component.reusablePortfolios.length).toBe(1);
      expect(component.reusablePortfolios[0].id).toBe(1);
    });
  });

  describe('openIntentModal() / selectIntent()', () => {
    it('loads intents from the backend', () => {
      brandSpy.getPromptIntents.and.returnValue(of([
        { slug: 'sales_deck', label: 'Sales Deck', expected_tone: 'Engaging', expected_duration_label: '10-15 min', narrative_style: 'x', visual_density: 'medium', preferred_layouts: ['cover_hero'] },
      ]));

      component.openIntentModal();

      expect(component.showIntentModal).toBeTrue();
      expect(component.promptIntents.length).toBe(1);
    });

    it('selecting an intent prefills the composer and switches to the composer modal', () => {
      const intent = {
        slug: 'sales_deck', label: 'Sales Deck', expected_tone: 'Engaging',
        expected_duration_label: '10-15 min', narrative_style: 'Customer-centric storytelling',
        visual_density: 'medium', preferred_layouts: ['cover_hero', 'case_study'],
      };
      component.showIntentModal = true;

      component.selectIntent(intent);

      expect(component.showIntentModal).toBeFalse();
      expect(component.showComposerModal).toBeTrue();
      expect(component.composerInitialValues).toEqual({
        objective: 'Sales Deck',
        tone: 'Engaging',
        story: 'Customer-centric storytelling',
        slide_type: 'cover_hero',
      });
    });
  });

  describe('generate() — prompt_metadata passthrough', () => {
    it('includes promptMetadata in the generation request when the composer was used', () => {
      component.prompt = 'Objective: X.';
      component.selectedStyle = 'style.pptx';
      component.selectedKnowledge = 'knowledge.pdf';
      component.promptMetadata = { objective: 'X', tone: 'Engaging' };
      brandSpy.generatePresentation.and.returnValue(of({ job_id: 1 }));

      component.generate();

      expect(brandSpy.generatePresentation).toHaveBeenCalledWith(jasmine.objectContaining({
        prompt_metadata: { objective: 'X', tone: 'Engaging' },
      }));
    });

    it('omits promptMetadata when the composer was never used', () => {
      component.prompt = 'plain manual prompt';
      component.selectedStyle = 'style.pptx';
      component.selectedKnowledge = 'knowledge.pdf';
      component.promptMetadata = null;
      brandSpy.generatePresentation.and.returnValue(of({ job_id: 1 }));

      component.generate();

      expect(brandSpy.generatePresentation).toHaveBeenCalledWith(jasmine.objectContaining({
        prompt_metadata: undefined,
      }));
    });
  });

  describe('reset()', () => {
    it('clears promptMetadata along with the rest of the generation state', () => {
      component.promptMetadata = { objective: 'X' };
      component.reset();
      expect(component.promptMetadata).toBeNull();
    });
  });

  describe('Ayuda 4 — openFavoritesModal() / useFavorite()', () => {
    it('loads favorites from the backend', () => {
      favoritesSpy.listFavorites.and.returnValue(of([
        { id: 1, title: 'Q3 Deck', prompt_text: 'x', prompt_metadata: null, source_job_id: null, owner_email: 'me@example.com', created_at: '', updated_at: '' },
      ]));

      component.openFavoritesModal();

      expect(component.showFavoritesModal).toBeTrue();
      expect(component.favoritesList.length).toBe(1);
    });

    it('useFavorite() applies prompt and metadata, and closes the modal on success', () => {
      component.prompt = '';
      component.showFavoritesModal = true;

      component.useFavorite({
        id: 1, title: 'Q3 Deck', prompt_text: 'Saved prompt', prompt_metadata: { objective: 'saved' },
        source_job_id: null, owner_email: 'me@example.com', created_at: '', updated_at: '',
      });

      expect(component.prompt).toBe('Saved prompt');
      expect(component.promptMetadata).toEqual({ objective: 'saved' });
      expect(component.showFavoritesModal).toBeFalse();
    });

    it('useFavorite() leaves state untouched and modal open when the user cancels the overwrite', () => {
      component.prompt = 'my own text';
      component.promptMetadata = null;
      component.showFavoritesModal = true;
      spyOn(window, 'confirm').and.returnValue(false);

      component.useFavorite({
        id: 1, title: 'Q3 Deck', prompt_text: 'Saved prompt', prompt_metadata: { objective: 'saved' },
        source_job_id: null, owner_email: 'me@example.com', created_at: '', updated_at: '',
      });

      expect(component.prompt).toBe('my own text');
      expect(component.promptMetadata).toBeNull();
      expect(component.showFavoritesModal).toBeTrue();
    });
  });

  describe('Ayuda 4 — openSaveFavoriteModal() / confirmSaveFavorite()', () => {
    it('opens the modal with a blank title and no error', () => {
      component.saveFavoriteTitle = 'stale';
      component.saveFavoriteError = 'stale error';

      component.openSaveFavoriteModal();

      expect(component.showSaveFavoriteModal).toBeTrue();
      expect(component.saveFavoriteTitle).toBe('');
      expect(component.saveFavoriteError).toBe('');
    });

    it('does nothing when the title is blank', () => {
      component.saveFavoriteTitle = '   ';
      component.confirmSaveFavorite();
      expect(favoritesSpy.createFavorite).not.toHaveBeenCalled();
    });

    it('creates the favorite with the current prompt and metadata, then closes the modal', () => {
      component.prompt = 'My current prompt';
      component.promptMetadata = { objective: 'X' };
      component.saveFavoriteTitle = 'My favorite';
      component.showSaveFavoriteModal = true;
      favoritesSpy.createFavorite.and.returnValue(of({
        id: 1, title: 'My favorite', prompt_text: 'My current prompt', prompt_metadata: { objective: 'X' },
        source_job_id: null, owner_email: 'me@example.com', created_at: '', updated_at: '',
      }));

      component.confirmSaveFavorite();

      expect(favoritesSpy.createFavorite).toHaveBeenCalledWith({
        title: 'My favorite', prompt_text: 'My current prompt', prompt_metadata: { objective: 'X' },
      });
      expect(component.showSaveFavoriteModal).toBeFalse();
      expect(component.savingFavorite).toBeFalse();
    });

    it('sets an error message and keeps the modal open when the request fails', () => {
      component.prompt = 'My current prompt';
      component.saveFavoriteTitle = 'My favorite';
      component.showSaveFavoriteModal = true;
      favoritesSpy.createFavorite.and.returnValue(throwError(() => new Error('500')));

      component.confirmSaveFavorite();

      expect(component.saveFavoriteError).toContain('Could not save');
      expect(component.showSaveFavoriteModal).toBeTrue();
      expect(component.savingFavorite).toBeFalse();
    });
  });
});
