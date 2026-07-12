import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { GeneratorComponent } from './generator.component';
import { BrandService } from '../../services/brand.service';
import { PromptFavoritesService } from '../../services/prompt-favorites.service';
import { AuthService } from '../../services/auth.service';

describe('GeneratorComponent — prompt support (soporte-indicaciones, biblioteca-prompts-favoritos)', () => {
  let fixture: ComponentFixture<GeneratorComponent>;
  let component: GeneratorComponent;
  let brandSpy: jasmine.SpyObj<BrandService>;

  beforeEach(async () => {
    brandSpy = jasmine.createSpyObj('BrandService', [
      'getBrands', 'getAvailableStyles', 'getAvailableKnowledge', 'getAvailableDialects', 'generatePresentation',
    ]);
    brandSpy.getBrands.and.returnValue(of([]));
    brandSpy.getAvailableStyles.and.returnValue(of({ styles: [] }));
    brandSpy.getAvailableKnowledge.and.returnValue(of({ sources: [] }));
    brandSpy.getAvailableDialects.and.returnValue(of([]));

    // PromptSupportComponent (embebido) también inyecta BrandService/PromptFavoritesService,
    // pero no dispara ninguna llamada hasta que se abre una de sus 4 tarjetas — no hace falta
    // stubear esos métodos acá, solo evitar que Angular falle construyendo el spy real.
    const favoritesSpy = jasmine.createSpyObj('PromptFavoritesService', ['listFavorites', 'createFavorite']);

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

  describe('onPromptSupportApply() — bridges <app-prompt-support> back into this component\'s own state', () => {
    it('applies the emitted text and metadata', () => {
      component.onPromptSupportApply({ text: 'Objective: X.', metadata: { objective: 'X' } });

      expect(component.prompt).toBe('Objective: X.');
      expect(component.promptMetadata).toEqual({ objective: 'X' });
    });

    it('accepts null metadata (e.g. a favorite saved from Template Merge, which has none)', () => {
      component.onPromptSupportApply({ text: 'Plain reused text', metadata: null });

      expect(component.prompt).toBe('Plain reused text');
      expect(component.promptMetadata).toBeNull();
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
});
